"""Find the red block with the camera, turn towards it and drive up to it.

Shows the camera loop: classical OpenCV runs fine on the Raspberry Pi. Colours differ on the
real camera, so expect to retune the HSV thresholds there.
"""

import cv2
from buildathon import Behavior, run

CLOSE_ENOUGH = 0.10  # stop when the block fills this fraction of the image


def find_red(image):
    """Return (horizontal offset -1..1, fraction of image covered), or None if not visible."""
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, (0, 120, 70), (10, 255, 255)) | cv2.inRange(hsv, (170, 120, 70), (180, 255, 255))
    moments = cv2.moments(mask, binaryImage=True)
    area = moments["m00"]
    height, width = mask.shape
    if area < 150:
        return None
    centre_x = moments["m10"] / area
    return (centre_x - width / 2) / (width / 2), area / (width * height)


class FollowRed(Behavior):
    rate_hz = 10

    def setup(self, robot):
        if not robot.base_enabled:
            raise SystemExit("The base is switched off (arm-only mode); this app needs it.")
        robot.arm.pose("home")  # fold the arm; only its yellow tip stays visible at the bottom of the frame

    def step(self, robot, obs):
        target = find_red(obs.image())
        if target is None:
            robot.drive(wz=30)  # search: turn on the spot
            return
        offset, size = target
        if size >= CLOSE_ENOUGH and abs(offset) < 0.2:
            print(f"reached the red block at t={obs.t:.1f}s")
            return False
        forward = 0.15 if abs(offset) < 0.4 else 0.0
        robot.drive(vx=forward, wz=-50 * offset)


if __name__ == "__main__":
    run(FollowRed())
