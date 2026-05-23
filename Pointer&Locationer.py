import sys
import math
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                               QPushButton, QFileDialog, QGroupBox, QComboBox, QLineEdit, QMessageBox, QMenu,
                               QSpinBox, QCheckBox, QColorDialog)
from PySide6.QtGui import QPixmap, QImage, QPainter, QPen, QColor, QFont, QCursor, QDoubleValidator
from PySide6.QtCore import Qt, QPointF, QRectF
from PIL import Image, ImageQt


class MapViewer(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        # 修改1：增大最小尺寸，适配大图片浏览
        self.setMinimumSize(1200, 600)

        self.image = None
        self.img_w = 0
        self.img_h = 0

        self.scale = 1.0
        self.tx = 0.0
        self.ty = 0.0
        self.min_scale = 0.05
        self.max_scale = 8.0

        self.dragging = False
        self.last_mouse_pos = QPointF()
        self.moved_since_press = False
        self.click_threshold = 5

        self.points = []  # 存储(QPointF, 自定义文字)元组
        self.lines = []
        self.ruler_visible = True

        # 标记样式
        self.point_diameter = 14
        self.point_fill_color = QColor(255, 0, 0)
        self.point_border_color = QColor(0, 0, 0)
        self.point_border_width = 1
        self.show_guide_lines = True

        # 文字样式
        self.show_coord_text = True
        self.show_custom_text = False
        self.custom_text = "标记"
        self.text_size = 11
        self.text_color = QColor(0, 0, 0)

        self.context_menu = None
        self.last_click_pos = None
        self.export_button = None
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)
        self.setCursor(Qt.CursorShape.ArrowCursor)

    # ------------------------------
    # 限制20字，接收实时文本
    # ------------------------------
    def set_custom_text(self, text):
        self.custom_text = text.strip()[:20]
        self.update()

    def set_point_diameter(self, v): self.point_diameter = max(2, v); self.update()
    def set_point_fill_color(self, c): self.point_fill_color = c; self.update()
    def set_point_border_color(self, c): self.point_border_color = c; self.update()
    def set_point_border_width(self, w): self.point_border_width = max(0, w); self.update()
    def set_show_guide_lines(self, b): self.show_guide_lines = b; self.update()
    def set_show_coord_text(self, b): self.show_coord_text = b; self.update()
    def set_show_custom_text(self, b): self.show_custom_text = b; self.update()
    def set_text_size(self, s): self.text_size = max(8, s); self.update()
    def set_text_color(self, c): self.text_color = c; self.update()

    def add_point(self, point, custom_text=""):
        """添加标记点，如果是偶数个点（即刚成对），自动计算并显示距离"""
        self.points.append((point, custom_text.strip()[:20]))
        if len(self.points) % 2 == 0 and len(self.points) > 1:
            self.lines.append((self.points[-2][0], self.points[-1][0]))
            # 新增：显示最后两个点之间的距离
            self.show_last_distance()
        self.update()

    def clear_points(self):
        self.points = []
        self.lines = []
        self.update()

    # ------------------------------
    # 距离计算（Haversine公式）
    # ------------------------------
    def calculate_distance_km(self, p1, p2):
        """计算地球上两点之间的距离（公里），输入为像素坐标QPointF"""
        if not self.image:
            return 0.0
        lon1, lat1 = self.pixel_to_coords(p1)
        lon2, lat2 = self.pixel_to_coords(p2)
        # 转换为弧度
        lat1_rad = math.radians(lat1)
        lat2_rad = math.radians(lat2)
        delta_lat = math.radians(lat2 - lat1)
        delta_lon = math.radians(lon2 - lon1)

        a = math.sin(delta_lat / 2) ** 2 + \
            math.cos(lat1_rad) * math.cos(lat2_rad) * \
            math.sin(delta_lon / 2) ** 2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        R = 6371  # 地球平均半径（公里）
        return R * c

    def show_last_distance(self):
        """显示最近添加的两个点之间的距离"""
        if len(self.points) < 2:
            return
        p1, _ = self.points[-2]
        p2, _ = self.points[-1]
        dist = self.calculate_distance_km(p1, p2)
        lon1, lat1 = self.pixel_to_coords(p1)
        lon2, lat2 = self.pixel_to_coords(p2)

        msg = (f"点1: {abs(lat1):.4f}°{'N' if lat1>=0 else 'S'}  "
               f"{abs(lon1):.4f}°{'E' if lon1>=0 else 'W'}\n"
               f"点2: {abs(lat2):.4f}°{'N' if lat2>=0 else 'S'}  "
               f"{abs(lon2):.4f}°{'E' if lon2>=0 else 'W'}\n\n"
               f"两点间距离: {dist:.2f} 公里")
        QMessageBox.information(self, "距离计算结果", msg)

    # ------------------------------
    # 2:1 图片加载
    # ------------------------------
    def load_image(self, file_path):
        try:
            Image.MAX_IMAGE_PIXELS = None
            pil_image = Image.open(file_path)
            self.img_w = pil_image.width
            self.img_h = pil_image.height
            ar = self.img_w / self.img_h
            if not math.isclose(ar, 2.0, rel_tol=1e-3):
                QMessageBox.warning(self, "比例错误", f"图片长宽比必须为2:1，当前为{ar:.3f}:1")
                return False
            self.image = QPixmap.fromImage(ImageQt.ImageQt(pil_image))
            self.reset_view_transform()
            self.clear_points()
            return True
        except Exception as e:
            QMessageBox.warning(self, "加载失败", f"图片无法打开：{str(e)}")
            return False

    def reset_view_transform(self):
        if not self.image: return
        w, h = self.width(), self.height()
        self.scale = min(w / self.img_w, h / self.img_h)
        self.scale = max(self.min_scale, min(self.scale, self.max_scale))
        sw, sh = self.img_w * self.scale, self.img_h * self.scale
        self.tx = (w - sw) / 2
        self.ty = (h - sh) / 2
        self.update()

    # ------------------------------
    # 绘制圆形点
    # ------------------------------
    def draw_circle(self, painter, x, y, d, fill, border, bw):
        painter.setBrush(fill)
        painter.setPen(QPen(border, bw) if bw > 0 else Qt.NoPen)
        painter.drawEllipse(QRectF(x - d / 2, y - d / 2, d, d))

    # ------------------------------
    # 安全文字绘制
    # ------------------------------
    def draw_text_safe(self, painter, x, y, lines, text_size, color, point_d):
        font = QFont("Arial", text_size)
        painter.setFont(font)
        painter.setPen(color)
        line_h = text_size + 4
        total_h = line_h * len(lines)
        start_y = y + point_d / 2 + 8
        rect_w = 400
        rect_x = x - rect_w / 2
        text_rect = QRectF(rect_x, start_y, rect_w, total_h + 4)
        painter.drawText(text_rect, Qt.AlignCenter, "\n".join(lines))

    def draw_point_and_lines(self, painter, point_data, img_x, img_y, sw, sh):
        point, txt = point_data
        s = self.scale
        px = img_x + point.x() * s
        py = img_y + point.y() * s
        d = self.point_diameter * s
        bw = self.point_border_width * s

        self.draw_circle(painter, px, py, d, self.point_fill_color, self.point_border_color, bw)

        if self.show_guide_lines:
            c = self.point_fill_color
            pen = QPen(QColor(c.red(), c.green(), c.blue(), 100), 1 * s, Qt.DashLine)
            painter.setPen(pen)
            painter.drawLine(QPointF(px, img_y), QPointF(px, img_y + sh))
            painter.drawLine(QPointF(img_x, py), QPointF(img_x + sw, py))

        lines = []
        if self.show_coord_text:
            lon, lat = self.pixel_to_coords(point)
            lon_dir = 'E' if lon >= 0 else 'W'
            lat_dir = 'N' if lat >= 0 else 'S'
            lines.append(f"{abs(lat):.3f}°{lat_dir} {abs(lon):.3f}°{lon_dir}")
        if self.show_custom_text and txt:
            lines.append(txt)

        if lines:
            self.draw_text_safe(painter, px, py, lines, self.text_size * s, self.text_color, d)

    # ------------------------------
    # 导出图片
    # ------------------------------
    def export_single_point_image(self, path, click_pos, current_custom_text):
        if not self.image: return False
        im = QImage(self.img_w, self.img_h, QImage.Format_ARGB32)
        im.fill(Qt.white)
        p = QPainter(im)
        p.setRenderHint(QPainter.Antialiasing)
        p.drawPixmap(0, 0, self.image)
        self.draw_ruler(p, 0, 0, self.img_w, self.img_h)

        ix = (click_pos.x() - self.tx) / self.scale
        iy = (click_pos.y() - self.ty) / self.scale
        if 0 <= ix < self.img_w and 0 <= iy < self.img_h:
            pt = QPointF(ix, iy)
            self.draw_circle(p, ix, iy, self.point_diameter,
                             self.point_fill_color, self.point_border_color, self.point_border_width)
            if self.show_guide_lines:
                c = self.point_fill_color
                p.setPen(QPen(QColor(c.red(), c.green(), c.blue(), 100), 1, Qt.DashLine))
                p.drawLine(QPointF(ix, 0), QPointF(ix, self.img_h))
                p.drawLine(QPointF(0, iy), QPointF(self.img_w, iy))

            lines = []
            if self.show_coord_text:
                lon, lat = self.pixel_to_coords(pt)
                lon_dir = 'E' if lon >= 0 else 'W'
                lat_dir = 'N' if lat >= 0 else 'S'
                lines.append(f"{abs(lat):.4f}°{lat_dir} {abs(lon):.4f}°{lon_dir}")
            if self.show_custom_text and current_custom_text:
                lines.append(current_custom_text.strip()[:20])

            if lines:
                self.draw_text_safe(p, ix, iy, lines, self.text_size, self.text_color, self.point_diameter)
        p.end()
        return im.save(path)

    def export_image(self, path):
        if not self.image: return False
        im = QImage(self.img_w, self.img_h, QImage.Format_ARGB32)
        im.fill(Qt.white)
        p = QPainter(im)
        p.setRenderHint(QPainter.Antialiasing)
        p.drawPixmap(0, 0, self.image)
        self.draw_ruler(p, 0, 0, self.img_w, self.img_h)

        for pt, txt in self.points:
            self.draw_circle(p, pt.x(), pt.y(), self.point_diameter,
                             self.point_fill_color, self.point_border_color, self.point_border_width)
            if self.show_guide_lines:
                c = self.point_fill_color
                p.setPen(QPen(QColor(c.red(), c.green(), c.blue(), 100), 1, Qt.DashLine))
                p.drawLine(QPointF(pt.x(), 0), QPointF(pt.x(), self.img_h))
                p.drawLine(QPointF(0, pt.y()), QPointF(self.img_w, pt.y()))

            lines = []
            if self.show_coord_text:
                lon, lat = self.pixel_to_coords(pt)
                lon_dir = 'E' if lon >= 0 else 'W'
                lat_dir = 'N' if lat >= 0 else 'S'
                lines.append(f"{abs(lat):.4f}°{lat_dir} {abs(lon):.4f}°{lon_dir}")
            if self.show_custom_text and txt:
                lines.append(txt)

            if lines:
                self.draw_text_safe(p, pt.x(), pt.y(), lines, self.text_size, self.text_color, self.point_diameter)

        for i, (a, b) in enumerate(self.lines):
            if i >= 3: break
            p.setPen(QPen(Qt.blue, 2))
            p.drawLine(a, b)
            lon1, lat1 = self.pixel_to_coords(a)
            lon2, lat2 = self.pixel_to_coords(b)
            d = self.calculate_distance_km(a, b)
            mx, my = (a.x() + b.x()) / 2, (a.y() + b.y()) / 2
            p.setPen(Qt.black)
            p.setFont(QFont("Arial", 12))
            p.drawText(QRectF(mx - 100, my - 12, 200, 24), Qt.AlignCenter, f"{d:.1f} km")
        p.end()
        return im.save(path)

    # ------------------------------
    # 坐标转换
    # ------------------------------
    def pixel_to_coords(self, pt):
        lon = (pt.x() / self.img_w) * 360 - 180
        lat = 90 - (pt.y() / self.img_h) * 180
        return lon, lat

    def coords_to_pixel(self, lon, lat):
        x = (lon + 180) / 360 * self.img_w
        y = (90 - lat) / 180 * self.img_h
        return QPointF(x, y)

    # ------------------------------
    # 标尺
    # ------------------------------
    def draw_ruler(self, p, ix, iy, iw, ih):
        p.setPen(Qt.black)
        p.setFont(QFont("Arial", 8))
        for v in range(0, 360, 30):
            x = ix + v / 360 * iw
            p.drawLine(QPointF(x, iy + ih), QPointF(x, iy + ih + 10))
            lon = v - 180
            p.drawText(QRectF(x - 15, iy + ih + 10, 30, 20), Qt.AlignCenter, f"{abs(lon)}°{'W' if lon < 0 else 'E'}")
        for v in range(0, 180, 30):
            y = iy + v / 180 * ih
            p.drawLine(QPointF(ix + iw, y), QPointF(ix + iw + 10, y))
            lat = 90 - v
            p.drawText(QRectF(ix + iw + 10, y - 10, 60, 20), Qt.AlignLeft, f"{abs(lat)}°{'S' if lat < 0 else 'N'}")

    # ------------------------------
    # 鼠标事件
    # ------------------------------
    def wheelEvent(self, e):
        if not self.image: return
        mp = e.position().toPoint()
        ipx = (mp.x() - self.tx) / self.scale
        ipy = (mp.y() - self.ty) / self.scale
        f = 1.1 if e.angleDelta().y() > 0 else 0.9
        ns = max(self.min_scale, min(self.scale * f, self.max_scale))
        self.tx = mp.x() - ns * ipx
        self.ty = mp.y() - ns * ipy
        self.scale = ns
        self.update()

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.dragging = True
            self.last_mouse_pos = e.pos()
            self.moved_since_press = False
            self.setCursor(Qt.ClosedHandCursor)
            self.last_click_pos = e.pos()
        return super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self.dragging and self.image:
            dx = e.x() - self.last_mouse_pos.x()
            dy = e.y() - self.last_mouse_pos.y()
            if abs(dx) + abs(dy) > self.click_threshold:
                self.moved_since_press = True
                self.tx += dx
                self.ty += dy
                self.last_mouse_pos = e.pos()
                self.update()
        return super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.dragging = False
            self.setCursor(Qt.ArrowCursor)
            if not self.moved_since_press:
                x = (e.x() - self.tx) / self.scale
                y = (e.y() - self.ty) / self.scale
                if 0 <= x < self.img_w and 0 <= y < self.img_h:
                    pt = QPointF(x, y)
                    self.add_point(pt, self.custom_text)
                    lon, lat = self.pixel_to_coords(pt)
                    QMessageBox.information(self, "坐标信息",
                        f"纬度: {abs(lat):.5f}°{'N' if lat>=0 else 'S'}\n"
                        f"经度: {abs(lon):.5f}°{'E' if lon>=0 else 'W'}")
                    self.create_export_button(e.pos())
        elif e.button() == Qt.RightButton:
            self.show_context_menu(e.pos())
        return super().mouseReleaseEvent(e)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), Qt.white)
        if self.image:
            sw, sh = int(self.img_w * self.scale), int(self.img_h * self.scale)
            p.drawPixmap(int(self.tx), int(self.ty), self.image.scaled(sw, sh, Qt.IgnoreAspectRatio, Qt.SmoothTransformation))
            if self.ruler_visible:
                self.draw_ruler(p, self.tx, self.ty, sw, sh)
            for pd in self.points:
                self.draw_point_and_lines(p, pd, self.tx, self.ty, sw, sh)
            for i, (a, b) in enumerate(self.lines):
                if i >= 3: break
                x1 = self.tx + a.x() * self.scale
                y1 = self.ty + a.y() * self.scale
                x2 = self.tx + b.x() * self.scale
                y2 = self.ty + b.y() * self.scale
                p.setPen(QPen(Qt.blue, 2 * self.scale))
                p.drawLine(QPointF(x1, y1), QPointF(x2, y2))
        p.end()

    # ------------------------------
    # 右键菜单与导出按钮
    # ------------------------------
    def create_context_menu(self):
        self.context_menu = QMenu(self)
        export_action = self.context_menu.addAction("导出此点图片")
        export_action.triggered.connect(self.export_current_point_image)
        return export_action

    def show_context_menu(self, pos):
        if not self.context_menu:
            self.create_context_menu()
        if self.last_click_pos:
            self.context_menu.popup(QCursor.pos())

    def create_export_button(self, pos):
        if self.export_button:
            self.export_button.deleteLater()
        self.export_button = QPushButton("导出", self)
        self.export_button.setFixedSize(60, 28)
        self.export_button.move(pos.x() - 30, pos.y() - 40)
        self.export_button.clicked.connect(self.export_current_point_image)
        self.export_button.show()

    def export_current_point_image(self):
        if not self.image or not self.last_click_pos:
            QMessageBox.warning(self, "错误", "没有可导出的图片或位置")
            return
        current_text = self.parent().ett.text() if hasattr(self.parent(), 'ett') else self.custom_text
        file_path, _ = QFileDialog.getSaveFileName(self, "导出当前标记图片", "", "PNG图片 (*.png)")
        if file_path:
            if not file_path.lower().endswith(".png"):
                file_path += ".png"
            if self.export_single_point_image(file_path, self.last_click_pos, current_text):
                QMessageBox.information(self, "导出成功", "图片已成功导出")
            else:
                QMessageBox.warning(self, "导出失败", "图片导出失败，请重试")
        if self.export_button:
            self.export_button.hide()


# ==============================
# 主窗口
# ==============================
class GlobalMapAnalyzer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("全球经纬度定位工具（两点距离计算）")
        # 修改2：增大初始窗口大小，更适配3600x1800图片
        self.setGeometry(100, 100, 1800, 900)
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)

        self.map = MapViewer(self)
        main_layout.addWidget(self.map, 1)

        # 控制面板
        control_panel = QGroupBox("控制面板")
        control_layout = QHBoxLayout(control_panel)
        main_layout.addWidget(control_panel)

        # 基础操作区
        basic_layout = QVBoxLayout()
        control_layout.addLayout(basic_layout)
        load_btn = QPushButton("导入2:1图片")
        load_btn.clicked.connect(self.load_image)
        basic_layout.addWidget(load_btn)
        clear_btn = QPushButton("清空标记")
        clear_btn.clicked.connect(self.map.clear_points)
        basic_layout.addWidget(clear_btn)
        export_btn = QPushButton("导出全部")
        export_btn.clicked.connect(self.export_all)
        basic_layout.addWidget(export_btn)

        # 坐标定位区
        coord_group = QGroupBox("坐标定位")
        coord_layout = QHBoxLayout(coord_group)
        control_layout.addWidget(coord_group)
        self.lat_dir = QComboBox()
        self.lat_dir.addItems(["N", "S"])
        coord_layout.addWidget(self.lat_dir)
        self.lat_input = QLineEdit()
        self.lat_input.setPlaceholderText("纬度 (0-90)")
        self.lat_input.setValidator(QDoubleValidator(0, 90, 6))
        coord_layout.addWidget(self.lat_input)
        self.lon_dir = QComboBox()
        self.lon_dir.addItems(["E", "W"])
        coord_layout.addWidget(self.lon_dir)
        self.lon_input = QLineEdit()
        self.lon_input.setPlaceholderText("经度 (0-180)")
        self.lon_input.setValidator(QDoubleValidator(0, 180, 6))
        coord_layout.addWidget(self.lon_input)
        locate_btn = QPushButton("定位标记")
        locate_btn.clicked.connect(self.locate_by_coords)
        coord_layout.addWidget(locate_btn)

        # 圆形标记设置区
        marker_group = QGroupBox("圆形标记")
        marker_layout = QVBoxLayout(marker_group)
        control_layout.addWidget(marker_group)
        size_layout = QHBoxLayout()
        marker_layout.addLayout(size_layout)
        size_layout.addWidget(QLabel("直径(px):"))
        self.point_diameter_spin = QSpinBox()
        self.point_diameter_spin.setRange(2, 100)
        self.point_diameter_spin.setValue(14)
        self.point_diameter_spin.valueChanged.connect(self.map.set_point_diameter)
        size_layout.addWidget(self.point_diameter_spin)
        size_layout.addWidget(QLabel("边框宽(px):"))
        self.border_width_spin = QSpinBox()
        self.border_width_spin.setRange(0, 10)
        self.border_width_spin.setValue(1)
        self.border_width_spin.valueChanged.connect(self.map.set_point_border_width)
        size_layout.addWidget(self.border_width_spin)

        color_layout = QHBoxLayout()
        marker_layout.addLayout(color_layout)
        color_layout.addWidget(QLabel("填充色:"))
        self.fill_color_btn = QPushButton()
        self.fill_color_btn.setStyleSheet("background-color: red;")
        self.fill_color_btn.clicked.connect(lambda: self.choose_color("fill"))
        color_layout.addWidget(self.fill_color_btn)
        color_layout.addWidget(QLabel("边框色:"))
        self.border_color_btn = QPushButton()
        self.border_color_btn.setStyleSheet("background-color: black;")
        self.border_color_btn.clicked.connect(lambda: self.choose_color("border"))
        color_layout.addWidget(self.border_color_btn)

        self.guide_lines_check = QCheckBox("显示经纬度辅助线")
        self.guide_lines_check.setChecked(True)
        self.guide_lines_check.toggled.connect(self.map.set_show_guide_lines)
        marker_layout.addWidget(self.guide_lines_check)

        # 文字设置区
        text_group = QGroupBox("文字设置（≤20字）")
        text_layout = QVBoxLayout(text_group)
        control_layout.addWidget(text_group)
        mode_layout = QHBoxLayout()
        text_layout.addLayout(mode_layout)
        self.coord_text_check = QCheckBox("显示自动坐标")
        self.coord_text_check.setChecked(True)
        self.coord_text_check.toggled.connect(self.map.set_show_coord_text)
        mode_layout.addWidget(self.coord_text_check)
        self.custom_text_check = QCheckBox("显示自定义文字")
        self.custom_text_check.setChecked(False)
        self.custom_text_check.toggled.connect(self.map.set_show_custom_text)
        mode_layout.addWidget(self.custom_text_check)

        text_layout.addWidget(QLabel("自定义文字内容:"))
        self.ett = QLineEdit()
        self.ett.setText("标记")
        self.ett.textChanged.connect(lambda new_text: self.map.set_custom_text(new_text))
        text_layout.addWidget(self.ett)

        style_layout = QHBoxLayout()
        text_layout.addLayout(style_layout)
        style_layout.addWidget(QLabel("文字大小(px):"))
        self.text_size_spin = QSpinBox()
        self.text_size_spin.setRange(8, 36)
        self.text_size_spin.setValue(11)
        self.text_size_spin.valueChanged.connect(self.map.set_text_size)
        style_layout.addWidget(self.text_size_spin)
        style_layout.addWidget(QLabel("文字颜色:"))
        self.text_color_btn = QPushButton()
        self.text_color_btn.setStyleSheet("background-color: black;")
        self.text_color_btn.clicked.connect(lambda: self.choose_color("text"))
        style_layout.addWidget(self.text_color_btn)

    # ------------------------------
    # 辅助方法
    # ------------------------------
    def choose_color(self, color_type):
        if color_type == "fill":
            current = self.map.point_fill_color
            title = "选择标记点填充色"
            callback = self.map.set_point_fill_color
            btn = self.fill_color_btn
        elif color_type == "border":
            current = self.map.point_border_color
            title = "选择标记点边框色"
            callback = self.map.set_point_border_color
            btn = self.border_color_btn
        else:
            current = self.map.text_color
            title = "选择文字颜色"
            callback = self.map.set_text_color
            btn = self.text_color_btn

        color = QColorDialog.getColor(current, self, title)
        if color.isValid():
            callback(color)
            btn.setStyleSheet(f"background-color: {color.name()};")

    def load_image(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择2:1比例图片", "",
            "图片文件 (*.png *.jpg *.jpeg *.bmp *.tif *.tiff)"
        )
        if file_path:
            self.map.load_image(file_path)

    def export_all(self):
        if not self.map.image:
            QMessageBox.warning(self, "错误", "请先导入图片")
            return
        file_path, _ = QFileDialog.getSaveFileName(self, "导出所有标记图片", "", "PNG图片 (*.png)")
        if file_path:
            if not file_path.lower().endswith(".png"):
                file_path += ".png"
            if self.map.export_image(file_path):
                QMessageBox.information(self, "导出成功", f"图片已导出到:\n{file_path}")
            else:
                QMessageBox.warning(self, "导出失败", "图片导出失败，请重试")

    def locate_by_coords(self):
        if not self.map.image:
            QMessageBox.warning(self, "错误", "请先导入图片")
            return
        try:
            lat_val = float(self.lat_input.text())
            lon_val = float(self.lon_input.text())
        except ValueError:
            QMessageBox.warning(self, "输入错误", "请输入有效的经纬度数值")
            return
        latitude = lat_val if self.lat_dir.currentText() == "N" else -lat_val
        longitude = lon_val if self.lon_dir.currentText() == "E" else -lon_val
        if not (-90 <= latitude <= 90) or not (-180 <= longitude <= 180):
            QMessageBox.warning(self, "范围错误", "纬度范围：-90°到90°\n经度范围：-180°到180°")
            return
        point = self.map.coords_to_pixel(longitude, latitude)
        self.map.add_point(point, self.ett.text())


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = GlobalMapAnalyzer()
    window.show()
    sys.exit(app.exec())