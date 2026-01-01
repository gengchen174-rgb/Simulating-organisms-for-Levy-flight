# Simulating-organisms-for-Levy-flight
This software is an agent-based model simulation tool specially designed for paleontological migration research. Its core goal is to transform the static performance parameters of paleontology quantified by biophysical model into dynamic and spatially explicit migration behavior and diffusion potential data in virtual paleogeographic environment.
# Marine Organism Levy Flight Simulation - Program Description

## What This Program Does

This is a simulation program that models how marine animals move and migrate across the world's oceans. It's like creating virtual sea creatures and watching how they travel.

## Key Features in Simple Terms

### 1. **Movement Patterns**
- Animals follow a special movement pattern called "Levy flight" - sometimes they take long journeys, sometimes they explore nearby areas
- You can adjust how much they prefer long vs short movements using the "Levy exponent" setting

### 2. **Global Ocean Environment**
- Uses a world map divided into 180×360 grid squares (like a detailed world map)
- Different ocean zones:
- <img width="3601" height="1801" alt="205Ma" src="https://github.com/user-attachments/assets/001b29db-2166-45d3-be17-ec6354ea8eb9" /><img width="1089" height="733" alt="屏幕截图 2025-12-31 101420" src="https://github.com/user-attachments/assets/b90dad75-564a-47ee-99d7-5bd51d5bbce1" />


  - **Coastal areas (G)**: Animals can refuel here
  - **Open ocean (B)**: Animals need to conserve energy
  - **Land (Y)**: Animals cannot go here
- Animals can travel across the entire world, including crossing the date line

### 3. **Smart Direction Choices**
- Animals can choose where to go based on water temperature (if temperature data is available)
- Follow the direction of ocean currents and occasionally return to random directions
- Or they can just choose random directions
- You can block certain directions (like "no going north")

### 4. **Ocean Currents**
- The program includes ocean currents that can push animals along
- You can turn this feature on or off

### 5. **Animal Survival Rules**
- Animals need to find coastal areas to refuel
- They have a maximum lifespan
- They die if they run out of energy or reach maximum age

### 6. **Complete Experiments**
- **Single experiments**: Test one set of conditions
- **Double experiments**: Run the same simulation twice with different movement patterns to compare results

## How to Use It

### Step 1: Setup
1. Install Python and required libraries
2. Prepare your map file (Excel format, 180 rows × 360 columns)
3. Optional: Prepare temperature data file

### Step 2: Run the Program
1. Start the program: `python ui_selector.py`<img width="1207" height="937" alt="屏幕截图 2025-12-31 103050" src="https://github.com/user-attachments/assets/ebf42bbe-07dc-404f-b8f8-3e0b5ecabc3d" />

2. A window opens with all settings
3. Choose your options:
   - How many animals to simulate
   - How long they should live
   - Whether to use temperature data
   - Whether to allow worldwide travel

### Step 3: Control Randomness (Important for Science!)
- **Direction Seed**: Controls which directions animals choose
- **Levy Seed**: Controls how long each movement step takes
- You can either:
  - Enter specific numbers (to get the same results every time)
  - Leave blank (program picks random numbers and tells you what they were)

### Step 4: Run and Watch
- Click "Run Simulation"
- Watch animals move across the map in real time
- See statistics about their survival and travel patterns
<img width="1502" height="834" alt="屏幕截图 2025-12-31 101937" src="https://github.com/user-attachments/assets/7f871481-21cb-40e2-aa15-572c6077bcbf" />

### Step 5: Save Results
- Export maps as picture files
- Export all data to Excel for analysis
- Save settings for next time

## Why This Program Is Useful

### For Scientific Research
- Study how ancient sea creatures might have migrated
- Test theories about animal movement patterns
- Compare different environmental conditions
- Because it records all random numbers used, other scientists can repeat your exact experiments

### For Education
- Visualize animal migration patterns
- Understand how ocean currents affect movement
- Explore how energy needs influence travel routes

## Special Notes

### Temperature Data Limitation
The program can use temperature to guide animal movement, but in practice, we don't have good temperature maps for ancient oceans (like the Triassic period 200 million years ago). So this feature is more of a "what if" tool than a realistic simulation for ancient times.

### Reproducibility
This is very important for science! The program gives you full control over random numbers. If you write down the "seeds" used, anyone can run the exact same simulation and get the same results.

### Flexibility
You can:
- After understanding the upper limit of stored energy, average movement speed, and the coordinate position you need to release, you can run the program
- Run detailed studies with 1000 animals and 100,000 time steps(This is not a fixed value; you can modify it)
- Compare different levy flignt movement strategies
- Test with or without ocean currents

## What Makes This Program Special

1. **Real global travel**: Animals can actually travel all the way around the world
2. **Smart movement**: Animals avoid land and seek favorable conditions
3. **Complete control**: Every aspect of the simulation can be adjusted
4. **Full documentation**: Every run records all settings for future reference
5. **Visual and data outputs**: Get both pictures and detailed spreadsheets

## In Simple Terms
Imagine you have virtual sea turtles. You decide:
- How fast they swim
- How they choose directions
- How long they can survive without food
- Whether ocean currents help them

Then you release them in the ocean and watch where they go, which ones survive, and how far they travel. The program lets you do this with hundreds of virtual animals at once and gives you all the data to analyze their journeys.

Perfect for studying animal migration patterns, testing scientific theories, or creating educational demonstrations of ocean ecology!
