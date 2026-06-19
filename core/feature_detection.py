import cv2
import numpy as np

from common import utils


class FeatureDetection:
    def __init__(self):
        self.SUSAN_HALF_WINDOW = 3
        self.HARRIS_BLOCK_SIZE = 2
        self.HARRIS_APERTURE_SIZE = 3

    # 无黑边旋转（白色填充+固定尺寸）
    def rotate_image(self, img, angle, scale=1.0, interp_method="bilinear"):
        if img is None:
            return None

        h, w = img.shape[:2]
        center = (w // 2, h // 2)

        interp = cv2.INTER_LINEAR if interp_method == "bilinear" else cv2.INTER_CUBIC
        M = cv2.getRotationMatrix2D(center, angle, scale)

        # 白色背景，彻底消除黑边
        rotated = cv2.warpAffine(img, M, (w, h), flags=interp, borderValue=(255, 255, 255))
        return rotated

    # 角点检测
    def harris_detect(self, gray, harris_k, threshold):
        gray_f = np.float32(gray)
        dst = cv2.cornerHarris(gray_f, self.HARRIS_BLOCK_SIZE, self.HARRIS_APERTURE_SIZE, harris_k)
        dst = cv2.dilate(dst, None)
        mask = dst > threshold * dst.max()
        return mask, int(np.sum(mask))

    def moravec_detect(self, gray, threshold):
        gray_f = gray.astype(np.float32)
        h, w = gray_f.shape
        shifts = [(1, 0), (0, 1), (1, 1), (-1, 1)]
        diffs = []
        for dx, dy in shifts:
            shifted = np.zeros_like(gray_f)
            if dx >= 0 and dy >= 0:
                shifted[dy:, dx:] = gray_f[: h - dy, : w - dx]
            elif dx < 0 and dy >= 0:
                shifted[dy:, : w + dx] = gray_f[: h - dy, -dx:]
            elif dx >= 0 and dy < 0:
                shifted[: h + dy, dx:] = gray_f[-dy:, : w - dx]
            else:
                shifted[: h + dy, : w + dx] = gray_f[-dy:, -dx:]
            diffs.append(np.square(gray_f - shifted))
        min_diff = np.min(diffs, axis=0)
        if min_diff.max() > 0:
            mask = min_diff > threshold * min_diff.max()
        else:
            mask = np.zeros_like(min_diff, dtype=bool)
        return mask, int(np.sum(mask))

    def forstner_detect(self, gray, threshold):
        gray_f = np.float32(gray)
        Ix = cv2.Sobel(gray_f, cv2.CV_32F, 1, 0, 3)
        Iy = cv2.Sobel(gray_f, cv2.CV_32F, 0, 1, 3)
        gIx2 = cv2.GaussianBlur(Ix**2, (3, 3), 1)
        gIy2 = cv2.GaussianBlur(Iy**2, (3, 3), 1)
        gIxy = cv2.GaussianBlur(Ix * Iy, (3, 3), 1)
        det = gIx2 * gIy2 - gIxy**2
        tr = gIx2 + gIy2 + 1e-8
        w = det / tr
        mask = w > threshold * w.max()
        return mask, int(np.sum(mask))

    def susan_detect(self, gray, susan_t, threshold):
        h, w = gray.shape
        mask = np.zeros_like(gray, dtype=bool)
        max_sim = int(36 * (1 - threshold))
        half = self.SUSAN_HALF_WINDOW

        for y in range(half, h - half):
            for x in range(half, w - half):
                win = gray[y - half : y + half + 1, x - half : x + half + 1]
                sim = np.sum(np.abs(win - gray[y, x]) < susan_t)
                if sim < max_sim:
                    mask[y, x] = True
        return mask, int(np.sum(mask))

    # 绘制特征点
    def draw_points(self, img, mask, point_size):
        out = img.copy()
        y, x = np.where(mask)
        for xi, yi in zip(x, y):
            cv2.circle(out, (xi, yi), point_size, (0, 0, 255), -1)
        return out

    # 加载/保存
    def load_image(self, path):
        return utils.imread_chinese(path)

    def save_image(self, img, path):
        utils.imwrite_chinese(path, img)
