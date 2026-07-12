import cv2
import numpy as np

img = cv2.imread(r"C:\Work\Code\Hermes_download\hermes-agent\scratch\user_video_midframe.png")
if img is None:
    print("Error: Could not read image.")
    exit(1)

# Convert to HSV
hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

# Calculate mean color
mean_color_bgr = cv2.mean(img)[:3]
print(f"Mean BGR Color: {mean_color_bgr}")

# Check green screen pixels (H: 35-85, S: 40-255, V: 40-255)
lower_green = np.array([35, 40, 40])
upper_green = np.array([85, 255, 255])
green_mask = cv2.inRange(hsv, lower_green, upper_green)
green_ratio = np.sum(green_mask > 0) / (img.shape[0] * img.shape[1])
print(f"Green screen pixel ratio: {green_ratio*100:.2f}%")

# Check blue screen pixels (H: 100-140)
lower_blue = np.array([100, 40, 40])
upper_blue = np.array([140, 255, 255])
blue_mask = cv2.inRange(hsv, lower_blue, upper_blue)
blue_ratio = np.sum(blue_mask > 0) / (img.shape[0] * img.shape[1])
print(f"Blue screen pixel ratio: {blue_ratio*100:.2f}%")
