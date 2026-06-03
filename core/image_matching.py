# core/image_matching.py
import cv2
import numpy as np
import os
from common.utils import put_chinese_text, non_max_suppression
from common.logger import logger
from common.exceptions import AlgorithmError

class ImageMatchingCore:
    """图像匹配核心算法类（无UI依赖）"""
    def __init__(self):
        # 预定义颜色（区分不同目标）
        self.colors = [
            (255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0),
            (255, 0, 255), (0, 255, 255), (255, 165, 0), (128, 0, 128)
        ]

    def load_image_with_chinese_path(self, file_path, is_color=True):
        """加载带中文路径的图像"""
        try:
            flag = cv2.IMREAD_COLOR if is_color else cv2.IMREAD_GRAYSCALE
            return cv2.imdecode(np.fromfile(file_path, dtype=np.uint8), flag)
        except Exception as e:
            logger.error(f"加载图像失败: {str(e)}", exc_info=True)
            raise AlgorithmError(f"加载图像失败: {str(e)}")

    def save_image_with_chinese_path(self, img, file_path):
        """保存图像到中文路径"""
        try:
            ext = os.path.splitext(file_path)[1].lower()
            cv2.imencode(ext, img)[1].tofile(file_path)
            return True
        except Exception as e:
            logger.error(f"保存图像失败: {str(e)}", exc_info=True)
            raise AlgorithmError(f"保存图像失败: {str(e)}")

    def single_matching(self, template_img, search_img, threshold):
        """单目标匹配（找最相似）"""
        try:
            logger.info("执行单目标匹配")
            # 灰度转换
            template_gray = cv2.cvtColor(template_img, cv2.COLOR_BGR2GRAY)
            search_gray = cv2.cvtColor(search_img, cv2.COLOR_BGR2GRAY)
            
            h_t, w_t = template_gray.shape
            h_s, w_s = search_gray.shape
            
            # 校验尺寸
            if h_t > h_s or w_t > w_s:
                raise ValueError("目标窗口尺寸不能大于搜索区域尺寸！")
            
            # 相关系数匹配
            result = cv2.matchTemplate(search_gray, template_gray, cv2.TM_CCOEFF_NORMED)
            min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
            
            # 计算坐标
            top_left = max_loc
            bottom_right = (top_left[0] + w_t, top_left[1] + h_t)
            center_point = (top_left[0] + w_t//2, top_left[1] + h_t//2)
            
            logger.info(f"单目标匹配完成，最大相关系数: {max_val:.4f}")
            
            # 封装结果
            return {
                "correlation_map": result,
                "max_val": max_val,
                "top_left": top_left,
                "bottom_right": bottom_right,
                "center_point": center_point,
                "threshold": threshold
            }
        except Exception as e:
            logger.error(f"单目标匹配失败: {str(e)}", exc_info=True)
            raise AlgorithmError(f"单目标匹配失败: {str(e)}")

    def single_multi_matching(self, template_img, search_img, threshold, nms_threshold):
        """单目标多匹配（找所有相似）"""
        try:
            logger.info("执行单目标多匹配")
            template_gray = cv2.cvtColor(template_img, cv2.COLOR_BGR2GRAY)
            search_gray = cv2.cvtColor(search_img, cv2.COLOR_BGR2GRAY)
            
            h_t, w_t = template_gray.shape
            h_s, w_s = search_gray.shape
            
            if h_t > h_s or w_t > w_s:
                raise ValueError("目标窗口尺寸不能大于搜索区域尺寸！")
            
            result = cv2.matchTemplate(search_gray, template_gray, cv2.TM_CCOEFF_NORMED)
            
            # 找出所有超过阈值的匹配位置
            locations = np.where(result >= threshold)
            boxes = []
            scores = []
            
            for pt in zip(*locations[::-1]):
                x1, y1 = pt
                x2 = x1 + w_t
                y2 = y1 + h_t
                boxes.append((x1, y1, x2, y2))
                scores.append(result[y1, x1])
            
            # 非极大值抑制
            keep_indices = non_max_suppression(boxes, scores, nms_threshold)
            
            logger.info(f"单目标多匹配完成，共找到{len(keep_indices)}个匹配点")
            
            # 封装结果
            return {
                "correlation_map": result,
                "boxes": [boxes[i] for i in keep_indices],
                "scores": [scores[i] for i in keep_indices],
                "threshold": threshold,
                "nms_threshold": nms_threshold,
                "total_count": len(keep_indices)
            }
        except Exception as e:
            logger.error(f"单目标多匹配失败: {str(e)}", exc_info=True)
            raise AlgorithmError(f"单目标多匹配失败: {str(e)}")

    def multi_target_matching(self, templates, search_img, threshold):
        """多目标匹配（各找一个）"""
        try:
            logger.info(f"执行多目标匹配，共{len(templates)}个目标")
            search_gray = cv2.cvtColor(search_img, cv2.COLOR_BGR2GRAY)
            h_s, w_s = search_gray.shape
            
            results = []
            
            # 遍历所有目标匹配
            for i, (template_img, filename, color) in enumerate(templates):
                template_gray = cv2.cvtColor(template_img, cv2.COLOR_BGR2GRAY)
                h_t, w_t = template_gray.shape
                
                if h_t > h_s or w_t > w_s:
                    results.append({
                        "filename": filename,
                        "status": "skip",
                        "reason": "尺寸过大"
                    })
                    continue
                
                result = cv2.matchTemplate(search_gray, template_gray, cv2.TM_CCOEFF_NORMED)
                min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
                
                # 计算坐标
                top_left = max_loc
                bottom_right = (top_left[0] + w_t, top_left[1] + h_t)
                center_point = (top_left[0] + w_t//2, top_left[1] + h_t//2)
                
                results.append({
                    "filename": filename,
                    "status": "success",
                    "max_val": max_val,
                    "top_left": top_left,
                    "bottom_right": bottom_right,
                    "center_point": center_point,
                    "color": color,
                    "size": (w_t, h_t),
                    "below_threshold": max_val < threshold
                })
            
            logger.info(f"多目标匹配完成，成功匹配{len([r for r in results if r['status'] == 'success'])}个目标")
            
            # 封装结果
            return {
                "results": results,
                "search_size": (w_s, h_s),
                "threshold": threshold
            }
        except Exception as e:
            logger.error(f"多目标匹配失败: {str(e)}", exc_info=True)
            raise AlgorithmError(f"多目标匹配失败: {str(e)}")

    def draw_single_match_result(self, search_img, result, filename, color):
        """绘制单目标匹配结果"""
        result_img = search_img.copy()
        cv2.rectangle(result_img, result["top_left"], result["bottom_right"], color, 3)
        cv2.circle(result_img, result["center_point"], 7, color, -1)
        
        # 添加文字
        text = f"{filename}: {result['max_val']:.4f}"
        text_position = (result["top_left"][0], result["top_left"][1] - 25)
        return put_chinese_text(result_img, text, text_position, 20, color)

    def draw_multi_match_result(self, search_img, result, color):
        """绘制单目标多匹配结果"""
        result_img = search_img.copy()
        
        for i, (box, score) in enumerate(zip(result["boxes"], result["scores"])):
            x1, y1, x2, y2 = box
            center_point = ((x1 + x2) // 2, (y1 + y2) // 2)
            
            cv2.rectangle(result_img, (x1, y1), (x2, y2), color, 2)
            cv2.circle(result_img, center_point, 6, color, -1)
            
            # 添加文字
            text = f"飞机{i+1}: {score:.4f}"
            text_position = (x1, y1 - 22)
            result_img = put_chinese_text(result_img, text, text_position, 18, color)
        
        return result_img

    def draw_multi_target_result(self, search_img, result):
        """绘制多目标匹配结果"""
        result_img = search_img.copy()
        
        for match in result["results"]:
            if match["status"] != "success":
                continue
                
            cv2.rectangle(result_img, match["top_left"], match["bottom_right"], match["color"], 3)
            cv2.circle(result_img, match["center_point"], 7, match["color"], -1)
            
            # 添加文字
            text = f"{match['filename']}: {match['max_val']:.4f}"
            text_position = (match["top_left"][0], match["top_left"][1] - 25)
            result_img = put_chinese_text(result_img, text, text_position, 20, match["color"])
        
        return result_img

# ==================== 向后兼容层（保留原来的函数名） ====================
def ncc_match(left_img, right_img, template, window_size=11, threshold=0.7):
    """原来的NCC匹配函数（兼容旧代码）"""
    # 提取模板区域
    x1, y1, x2, y2 = template
    template_img = left_img[y1:y2, x1:x2]
    
    core = ImageMatchingCore()
    result = core.single_matching(template_img, right_img, threshold)
    
    # 转换为原来的返回格式
    matches = []
    if result["max_val"] >= threshold:
        matches.append((
            result["top_left"][0], result["top_left"][1],
            result["center_point"][0], result["center_point"][1],
            result["max_val"]
        ))
    
    return matches

def nms(matches, threshold=0.3):
    """原来的非极大值抑制函数（兼容旧代码）"""
    if len(matches) == 0:
        return []
    
    boxes = []
    scores = []
    for match in matches:
        x, y, cx, cy, score = match
        # 假设模板大小为11x11
        boxes.append((x, y, x+11, y+11))
        scores.append(score)
    
    keep_indices = non_max_suppression(boxes, scores, threshold)
    return [matches[i] for i in keep_indices]

def draw_matches(left_img, right_img, matches):
    """原来的绘制匹配结果函数（兼容旧代码）"""
    # 拼接左右图像
    h1, w1 = left_img.shape[:2]
    h2, w2 = right_img.shape[:2]
    h = max(h1, h2)
    result = np.zeros((h, w1 + w2, 3), dtype=np.uint8)
    result[:h1, :w1] = left_img
    result[:h2, w1:] = right_img
    
    # 绘制匹配线
    for match in matches:
        x1, y1, x2, y2, score = match
        # 左图点（模板中心）
        cx1 = x1 + 5
        cy1 = y1 + 5
        # 右图点
        cx2 = w1 + x2 + 5
        cy2 = y2 + 5
        
        cv2.line(result, (cx1, cy1), (cx2, cy2), (0, 255, 0), 1)
        cv2.circle(result, (cx1, cy1), 3, (0, 0, 255), -1)
        cv2.circle(result, (cx2, cy2), 3, (0, 0, 255), -1)
    
    return result

def draw_heatmap(img, matches):
    """原来的绘制热力图函数（兼容旧代码）"""
    heatmap = np.zeros(img.shape[:2], dtype=np.float32)
    
    for match in matches:
        x, y, cx, cy, score = match
        heatmap[y:y+11, x:x+11] = score
    
    # 归一化
    heatmap = (heatmap - heatmap.min()) / (heatmap.max() - heatmap.min() + 1e-8)
    
    # 转换为彩色热力图
    heatmap_color = cv2.applyColorMap((heatmap * 255).astype(np.uint8), cv2.COLORMAP_JET)
    
    # 与原图混合
    result = cv2.addWeighted(img, 0.7, heatmap_color, 0.3, 0)
    return result