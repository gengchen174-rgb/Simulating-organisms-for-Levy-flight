import sys
import math
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                               QPushButton, QFileDialog, QGroupBox, QComboBox, QLineEdit, QMessageBox)
from PySide6.QtGui import QPixmap, QImage, QPainter, QPen, QColor, QFont, QCursor
from PySide6.QtCore import Qt, QPointF, QSize, QPoint
from PIL import Image, ImageQt  # 添加Pillow库支持TIFF格式


class MapViewer(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(800, 400)

        # 原始图像（像素坐标系）
        self.image = None  # QPixmap of original image
        self.img_w = 0
        self.img_h = 0

        # 视图变换参数 (widget坐标系)
        self.scale = 1.0       # 当前缩放倍数，相对于原始图片像素
        self.tx = 0.0          # 图片左上角在widget中的x坐标
        self.ty = 0.0          # 图片左上角在widget中的y坐标
        self.min_scale = 0.05
        self.max_scale = 8.0

        # 交互状态
        self.dragging = False          # 是否正在拖拽（用于平移）
        self.last_mouse_pos = QPoint() # 上一次鼠标位置（用于计算平移增量）
        self.moved_since_press = False # 按下后是否有显著移动（用于判断是点击还是拖拽）
        self.click_threshold = 5       # px

        # 绘制元素（均以原始图片像素坐标保存）
        self.points = []
        self.lines = []
        self.ruler_visible = True
        self.font = QFont("Arial", 10)

        # 光标样式
        self.setCursor(Qt.CursorShape.ArrowCursor)

    def load_image(self, file_path):
        # 使用Pillow加载图片（支持TIFF格式）
        try:
            pil_image = Image.open(file_path)
            if pil_image.width != 3601 or pil_image.height != 1801:
                return False

            # 将PIL图像转换为QPixmap
            qimage = ImageQt.ImageQt(pil_image)
            self.image = QPixmap.fromImage(qimage)
            self.img_w = self.image.width()
            self.img_h = self.image.height()

            # 初始化变换：按窗口大小适配并居中
            self.reset_view_transform()

            self.points = []
            self.lines = []
            self.update()
            return True
        except Exception as e:
            print(f"加载图片失败: {e}")
            return False

    def reset_view_transform(self):
        """在加载图片或窗口大小变化时，初始化 scale/tX/tY 以适配并居中图片"""
        if not self.image:
            return
        w = max(1, self.width())
        h = max(1, self.height())
        # 适配模式：初始缩放使图片完整显示
        self.scale = min(w / self.img_w, h / self.img_h)
        # 限制在 min/max 范围内
        self.scale = max(self.min_scale, min(self.scale, self.max_scale))
        # 居中
        scaled_w = self.img_w * self.scale
        scaled_h = self.img_h * self.scale
        self.tx = (w - scaled_w) / 2.0
        self.ty = (h - scaled_h) / 2.0

    def resizeEvent(self, event):
        # 在窗口尺寸改变时保持当前缩放（不自动重新适配）
        # 但是如果还没有图像或scale很大/小，还是调用 reset
        if not self.image:
            return super().resizeEvent(event)
        # 保持当前中心点不变 —— 简单策略：不改变 scale，且不移动图片位置
        self.update()

    def add_point(self, point):
        """point: QPointF in original image pixel coordinates"""
        self.points.append(point)
        if len(self.points) % 2 == 0 and len(self.points) > 1:
            # 每两个点组成一条线
            self.lines.append((self.points[-2], self.points[-1]))
        self.update()

    def clear_points(self):
        self.points = []
        self.lines = []
        self.update()

    def pixel_to_coords(self, point):
        """把原始图片像素坐标（QPointF）转换为经纬度"""
        if not self.image:
            return (0, 0)

        img_width = self.img_w
        img_height = self.img_h

        longitude = (point.x() / img_width) * 360 - 180
        latitude = 90 - (point.y() / img_height) * 180

        return (longitude, latitude)

    def coords_to_pixel(self, longitude, latitude):
        """把经纬度转换为原始图片像素坐标 QPointF"""
        if not self.image:
            return QPointF(0, 0)

        img_width = self.img_w
        img_height = self.img_h

        x = (longitude + 180) / 360 * img_width
        y = (90 - latitude) / 180 * img_height

        return QPointF(x, y)

    def haversine_distance(self, lon1, lat1, lon2, lat2):
        # 将经纬度转换为弧度
        lon1, lat1, lon2, lat2 = map(math.radians, [lon1, lat1, lon2, lat2])

        # 计算差值
        dlon = lon2 - lon1
        dlat = lat2 - lat1

        # Haversine公式
        a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
        c = 2 * math.asin(math.sqrt(a))

        # 地球半径(公里)
        r = 6371
        return c * r

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 绘制背景
        painter.fillRect(self.rect(), Qt.GlobalColor.white)

        if self.image:
            # 根据当前 scale 和 tx/ty 绘制图片
            scaled_w = int(self.img_w * self.scale)
            scaled_h = int(self.img_h * self.scale)

            # 减少每帧缩放开销：使用 QPixmap.scaled 进行平滑绘制
            scaled_pix = self.image.scaled(scaled_w, scaled_h,
                                          Qt.AspectRatioMode.IgnoreAspectRatio,
                                          Qt.TransformationMode.SmoothTransformation)

            painter.drawPixmap(int(self.tx), int(self.ty), scaled_pix)

            # 绘制标尺
            if self.ruler_visible:
                self.draw_ruler(painter, self.tx, self.ty, scaled_w, scaled_h)

            # 绘制点和经纬线 (points 存储为原始像素坐标)
            for point in self.points:
                self.draw_point_and_lines(painter, point, self.tx, self.ty, scaled_w, scaled_h)

            # 绘制连线
            for i, line in enumerate(self.lines):
                if i < 3:  # 只允许三组连线
                    self.draw_line(painter, line[0], line[1], self.tx, self.ty, scaled_w, scaled_h)

    def draw_point_and_lines(self, painter, point, img_x, img_y, img_width, img_height):
        # 计算在缩放后图片上的位置
        scale = self.scale

        px = img_x + point.x() * scale
        py = img_y + point.y() * scale

        # 绘制红点
        painter.setPen(QPen(Qt.GlobalColor.red, 7, Qt.PenStyle.SolidLine))
        painter.drawPoint(int(px), int(py))

        # 绘制经纬线
        painter.setPen(QPen(QColor(255, 0, 0, 100), 1, Qt.PenStyle.DashLine))

        # 经线 (垂直线)
        painter.drawLine(int(px), int(img_y), int(px), int(img_y + img_height))

        # 纬线 (水平线)
        painter.drawLine(int(img_x), int(py), int(img_x + img_width), int(py))

    def draw_line(self, painter, p1, p2, img_x, img_y, img_width, img_height):
        scale = self.scale
        x1 = img_x + p1.x() * scale
        y1 = img_y + p1.y() * scale
        x2 = img_x + p2.x() * scale
        y2 = img_y + p2.y() * scale

        # 绘制连线
        painter.setPen(QPen(Qt.GlobalColor.blue, 2, Qt.PenStyle.SolidLine))
        painter.drawLine(int(x1), int(y1), int(x2), int(y2))

        # 计算距离 (使用原始像素 -> 经纬度 -> haversine)
        lon1, lat1 = self.pixel_to_coords(p1)
        lon2, lat2 = self.pixel_to_coords(p2)
        distance = self.haversine_distance(lon1, lat1, lon2, lat2)

        # 在连线中点显示距离
        mid_x = (x1 + x2) / 2
        mid_y = (y1 + y2) / 2
        painter.setPen(Qt.GlobalColor.black)
        painter.setFont(self.font)
        painter.drawText(int(mid_x), int(mid_y), f"{distance:.1f} km")

    def draw_ruler(self, painter, img_x, img_y, img_width, img_height):
        # 设置标尺样式
        painter.setPen(QPen(Qt.GlobalColor.black, 1, Qt.PenStyle.SolidLine))
        painter.setFont(QFont("Arial", 8))

        # 经度标尺 (底部)
        for i in range(0, 360, 30):
            x = img_x + (i / 360) * img_width
            painter.drawLine(int(x), int(img_y + img_height), int(x), int(img_y + img_height + 10))

            lon = i - 180
            lon_label = f"{abs(lon)}°{'W' if lon < 0 else 'E'}"
            painter.drawText(int(x) - 15, int(img_y + img_height + 25), lon_label)

        # 纬度标尺 (右侧)
        for i in range(0, 180, 30):
            y = img_y + (i / 180) * img_height
            painter.drawLine(int(img_x + img_width), int(y), int(img_x + img_width + 10), int(y))

            lat = 90 - i
            lat_label = f"{abs(lat)}°{'S' if lat < 0 else 'N'}"
            painter.drawText(int(img_x + img_width + 15), int(y) + 5, lat_label)

    def export_image(self, file_path):
        if not self.image:
            return False

        # 创建导出图像（原始尺寸）
        export_img = QImage(self.img_w, self.img_h, QImage.Format.Format_ARGB32)
        export_img.fill(Qt.GlobalColor.white)

        painter = QPainter(export_img)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 绘制原始图片
        painter.drawPixmap(0, 0, self.image)

        # 绘制标尺（原始像素坐标）
        self.draw_ruler(painter, 0, 0, self.img_w, self.img_h)

        # 绘制点和经纬线（使用原始像素坐标）
        for point in self.points:
            painter.setPen(QPen(Qt.GlobalColor.red, 7, Qt.PenStyle.SolidLine))
            painter.drawPoint(int(point.x()), int(point.y()))

            painter.setPen(QPen(QColor(255, 0, 0, 100), 1, Qt.PenStyle.DashLine))
            painter.drawLine(int(point.x()), 0, int(point.x()), self.img_h)
            painter.drawLine(0, int(point.y()), self.img_w, int(point.y()))

        # 绘制连线并显示距离
        for i, line in enumerate(self.lines):
            if i < 3:
                p1, p2 = line
                painter.setPen(QPen(Qt.GlobalColor.blue, 2, Qt.PenStyle.SolidLine))
                painter.drawLine(int(p1.x()), int(p1.y()), int(p2.x()), int(p2.y()))

                lon1, lat1 = self.pixel_to_coords(p1)
                lon2, lat2 = self.pixel_to_coords(p2)
                distance = self.haversine_distance(lon1, lat1, lon2, lat2)

                mid_x = (p1.x() + p2.x()) / 2
                mid_y = (p1.y() + p2.y()) / 2
                painter.setPen(Qt.GlobalColor.black)
                painter.setFont(QFont("Arial", 12))
                painter.drawText(int(mid_x), int(mid_y), f"{distance:.1f} km")

        painter.end()
        return export_img.save(file_path)

    # ----------------------------
    # 交互事件： 鼠标滚轮缩放 / 鼠标按下移动释放（点击或平移）
    # ----------------------------
    def wheelEvent(self, event):
        if not self.image:
            return

        # 鼠标在widget中的位置（QPoint）
        mouse_pos = event.position().toPoint()

        # 鼠标在图片上的相对坐标（相对于原始像素，用于保持缩放中心）
        # 先检查鼠标是否在图片可视区域内
        if not (self.tx <= mouse_pos.x() <= self.tx + self.img_w * self.scale and
                self.ty <= mouse_pos.y() <= self.ty + self.img_h * self.scale):
            # 如果鼠标不在图片区域，我们依然允许以鼠标为中心缩放，但这里会导致图像相对位置变化
            pass

        # 计算鼠标指向的原始像素坐标（浮点）
        img_px = (mouse_pos.x() - self.tx) / self.scale
        img_py = (mouse_pos.y() - self.ty) / self.scale

        # 缩放因子（每个滚轮刻度）
        num_degrees = event.angleDelta().y() / 8.0
        num_steps = num_degrees / 15.0
        factor = 1.0 + (0.15 * num_steps)  # 15% 每步（可调整）

        new_scale = self.scale * factor
        new_scale = max(self.min_scale, min(self.max_scale, new_scale))
        factor = new_scale / self.scale  # 实际应用的因子（考虑边界）

        # 为了在缩放后使鼠标位置指向同一原始像素，更新 tx, ty：
        # mouse_pos = (tx,ty) + scale * (img_px, img_py)
        # 目标: mouse_pos = (tx',ty') + new_scale * (img_px, img_py)
        # => tx' = mouse_pos.x() - new_scale * img_px
        self.tx = mouse_pos.x() - new_scale * img_px
        self.ty = mouse_pos.y() - new_scale * img_py

        self.scale = new_scale
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.dragging = True
            self.last_mouse_pos = event.pos()
            self.moved_since_press = False
            # 切换光标提示
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
        return super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if not self.image:
            return super().mouseMoveEvent(event)

        if self.dragging:
            # 计算移动距离
            cur = event.pos()
            dx = cur.x() - self.last_mouse_pos.x()
            dy = cur.y() - self.last_mouse_pos.y()
            # 如果移动超过阈值，认为是平移动作
            if abs(dx) > self.click_threshold or abs(dy) > self.click_threshold:
                self.moved_since_press = True
                # 更新平移偏移 tx/ty
                self.tx += dx
                self.ty += dy
                self.last_mouse_pos = cur
                self.update()
        return super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.dragging = False
            self.setCursor(Qt.CursorShape.ArrowCursor)

            # 如果没有显著移动，视为点击 -> 添加点（若点击在图片内）
            release_pos = event.pos()
            if not self.moved_since_press:
                # 计算原始像素坐标
                img_x = (release_pos.x() - self.tx) / self.scale
                img_y = (release_pos.y() - self.ty) / self.scale

                # 检查是否在图片范围内
                if 0 <= img_x < self.img_w and 0 <= img_y < self.img_h:
                    # 添加点（使用原始像素坐标）
                    self.add_point(QPointF(img_x, img_y))

                    lon, lat = self.pixel_to_coords(QPointF(img_x, img_y))
                    lat_dir = "N" if lat >= 0 else "S"
                    lon_dir = "E" if lon >= 0 else "W"

                    QMessageBox.information(
                        self.window(), "坐标信息",
                        f"纬度: {abs(lat):.6f}°{lat_dir}\n"
                        f"经度: {abs(lon):.6f}°{lon_dir}"
                    )
        return super().mouseReleaseEvent(event)


class GlobalMapAnalyzer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("全球海路图分析工具")
        self.setGeometry(100, 100, 1960, 1080)

        # 创建主部件和布局
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout()
        main_widget.setLayout(main_layout)

        # 创建地图查看器
        self.map_viewer = MapViewer()
        main_layout.addWidget(self.map_viewer, 1)

        # 创建控制面板
        control_panel = QGroupBox("控制面板")
        control_layout = QHBoxLayout()
        control_panel.setLayout(control_layout)
        main_layout.addWidget(control_panel)

        # 添加按钮
        self.load_button = QPushButton("导入图片")
        self.load_button.clicked.connect(self.load_image)
        control_layout.addWidget(self.load_button)

        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.clicked.connect(self.refresh)
        control_layout.addWidget(self.refresh_button)

        self.export_button = QPushButton("Point")
        self.export_button.clicked.connect(self.export_image)
        control_layout.addWidget(self.export_button)

        # 添加坐标输入控件
        coord_group = QGroupBox("坐标定位")
        coord_layout = QHBoxLayout()
        coord_group.setLayout(coord_layout)
        control_layout.addWidget(coord_group)

        # 纬度输入
        self.lat_dir = QComboBox()
        self.lat_dir.addItems(["N", "S"])
        coord_layout.addWidget(self.lat_dir)

        self.lat_input = QLineEdit()
        self.lat_input.setPlaceholderText("纬度 (0-90)")
        self.lat_input.setValidator(self.create_coord_validator(0, 90))
        coord_layout.addWidget(self.lat_input)

        # 经度输入
        self.lon_dir = QComboBox()
        self.lon_dir.addItems(["W", "E"])
        coord_layout.addWidget(self.lon_dir)

        self.lon_input = QLineEdit()
        self.lon_input.setPlaceholderText("经度 (0-180)")
        self.lon_input.setValidator(self.create_coord_validator(0, 180))
        coord_layout.addWidget(self.lon_input)

        self.locate_button = QPushButton("定位")
        self.locate_button.clicked.connect(self.locate_by_coords)
        coord_layout.addWidget(self.locate_button)

    def create_coord_validator(self, min_val, max_val):
        from PySide6.QtGui import QDoubleValidator
        validator = QDoubleValidator()
        validator.setRange(min_val, max_val, 6)
        validator.setNotation(QDoubleValidator.Notation.StandardNotation)
        return validator

    def load_image(self):
        # 添加TIFF格式支持
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择海路图", "",
            "图片文件 (*.png *.jpg *.jpeg *.bmp *.tif *.tiff)"
        )

        if file_path:
            if not self.map_viewer.load_image(file_path):
                QMessageBox.warning(
                    self, "分辨率错误",
                    "图片分辨率必须是3601×1801像素，请重新选择图片。"
                )

    def refresh(self):
        self.map_viewer.clear_points()

    def export_image(self):
        if not self.map_viewer.image:
            QMessageBox.warning(self, "错误", "请先导入图片")
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self, "导出图片", "", "PNG图片 (*.png)"
        )

        if file_path:
            if not file_path.lower().endswith('.png'):
                file_path += '.png'

            if self.map_viewer.export_image(file_path):
                QMessageBox.information(self, "导出成功", f"图片已导出到:\n{file_path}")
            else:
                QMessageBox.warning(self, "导出失败", "图片导出失败，请重试")

    def locate_by_coords(self):
        if not self.map_viewer.image:
            QMessageBox.warning(self, "错误", "请先导入图片")
            return

        try:
            lat_val = float(self.lat_input.text())
            lon_val = float(self.lon_input.text())
        except ValueError:
            QMessageBox.warning(self, "输入错误", "请输入有效的经纬度数值")
            return

        # 处理方向
        latitude = lat_val if self.lat_dir.currentText() == "N" else -lat_val
        longitude = lon_val if self.lon_dir.currentText() == "E" else -lon_val

        # 验证范围
        if not (-90 <= latitude <= 90) or not (-180 <= longitude <= 180):
            QMessageBox.warning(self, "范围错误", "纬度范围: -90°到90°\n经度范围: -180°到180°")
            return

        # 转换为像素坐标 (原始图片像素坐标系)
        point = self.map_viewer.coords_to_pixel(longitude, latitude)
        self.map_viewer.add_point(point)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = GlobalMapAnalyzer()
    window.show()
    sys.exit(app.exec())
