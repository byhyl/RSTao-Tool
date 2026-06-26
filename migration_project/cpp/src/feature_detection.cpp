#include "rstao/feature_detection.hpp"

#include <opencv2/imgproc.hpp>
#include <opencv2/calib3d.hpp>

#include <cmath>
#include <stdexcept>

namespace rstao {

namespace {

void validateGray(const cv::Mat& src) {
    if (src.empty())
        throw std::invalid_argument("Source image is empty");
    if (src.channels() != 1)
        throw std::invalid_argument("Feature detection requires single-channel (grayscale) image");
}

// Produce binary mask from float response map
CornerResult maskFromResponse(const cv::Mat& response, double threshold) {
    double minVal, maxVal;
    cv::minMaxLoc(response, &minVal, &maxVal);
    double thresh = minVal + (maxVal - minVal) * threshold;

    CornerResult cr;
    cr.mask = cv::Mat::zeros(response.size(), CV_8UC1);
    for (int y = 0; y < response.rows; ++y) {
        const float* row = response.ptr<float>(y);
        uchar* maskRow = cr.mask.ptr<uchar>(y);
        for (int x = 0; x < response.cols; ++x) {
            if (row[x] > thresh) {
                maskRow[x] = 255;
            }
        }
    }
    cr.count = cv::countNonZero(cr.mask);
    return cr;
}

// Non-maximum suppression on a mask (simple 3x3)
void simpleNMS(cv::Mat& mask) {
    cv::Mat dilated;
    cv::dilate(mask, dilated, cv::Mat());
    for (int y = 0; y < mask.rows; ++y) {
        uchar* mRow = mask.ptr<uchar>(y);
        const uchar* dRow = dilated.ptr<uchar>(y);
        for (int x = 0; x < mask.cols; ++x) {
            if (mRow[x] && dRow[x] > mRow[x]) {
                mRow[x] = 0;
            }
        }
    }
}

cv::Mat sobelResponse(const cv::Mat& gray) {
    cv::Mat gx, gy;
    cv::Sobel(gray, gx, CV_32F, 1, 0, 3);
    cv::Sobel(gray, gy, CV_32F, 0, 1, 3);
    cv::Mat mag;
    cv::magnitude(gx, gy, mag);
    return mag;
}

} // anonymous namespace

// ============================================================================
// Harris
// ============================================================================

CornerResult detect_harris(const GrayImage& src, double k, double threshold) {
    validateGray(src);
    cv::Mat floatSrc;
    src.convertTo(floatSrc, CV_32F);

    cv::Mat harris;
    cv::cornerHarris(floatSrc, harris, 3, 3, k);

    auto result = maskFromResponse(harris, threshold);
    simpleNMS(result.mask);
    result.count = cv::countNonZero(result.mask);
    return result;
}

// ============================================================================
// Moravec
// ============================================================================

CornerResult detect_moravec(const GrayImage& src, double threshold) {
    validateGray(src);
    cv::Mat gray = src;
    int w = 3; // window half-size

    cv::Mat response(gray.size(), CV_32F, cv::Scalar(0));

    for (int y = w; y < gray.rows - w; ++y) {
        const uchar* row = gray.ptr<uchar>(y);
        float* respRow = response.ptr<float>(y);

        for (int x = w; x < gray.cols - w; ++x) {
            double minSSD = std::numeric_limits<double>::max();

            // 4 directions: (dx, dy) = (1,0), (0,1), (1,1), (1,-1)
            const int dirs[4][2] = {{1,0}, {0,1}, {1,1}, {1,-1}};
            for (int d = 0; d < 4; ++d) {
                int dx = dirs[d][0];
                int dy = dirs[d][1];
                double ssd = 0.0;
                for (int wy = -w; wy <= w; ++wy) {
                    const uchar* row1 = gray.ptr<uchar>(y + wy);
                    const uchar* row2 = gray.ptr<uchar>(y + wy + dy);
                    for (int wx = -w; wx <= w; ++wx) {
                        double diff = static_cast<double>(row1[x + wx]) - row2[x + wx + dx];
                        ssd += diff * diff;
                    }
                }
                if (ssd < minSSD) minSSD = ssd;
            }
            respRow[x] = static_cast<float>(minSSD);
        }
    }

    return maskFromResponse(response, threshold);
}

// ============================================================================
// Forstner
// ============================================================================

CornerResult detect_forstner(const GrayImage& src, double threshold) {
    validateGray(src);

    cv::Mat gx, gy;
    cv::Sobel(src, gx, CV_32F, 1, 0, 3);
    cv::Sobel(src, gy, CV_32F, 0, 1, 3);

    cv::Mat gx2, gy2, gxy;
    cv::multiply(gx, gx, gx2);
    cv::multiply(gy, gy, gy2);
    cv::multiply(gx, gy, gxy);

    int w = 3;
    cv::Mat response(src.size(), CV_32F, cv::Scalar(0));

    for (int y = w; y < src.rows - w; ++y) {
        float* respRow = response.ptr<float>(y);
        for (int x = w; x < src.cols - w; ++x) {
            cv::Rect roi(x - w, y - w, 2 * w + 1, 2 * w + 1);
            double sumGx2  = cv::sum(gx2(roi))[0];
            double sumGy2  = cv::sum(gy2(roi))[0];
            double sumGxy  = cv::sum(gxy(roi))[0];

            double trace = sumGx2 + sumGy2;
            double det   = sumGx2 * sumGy2 - sumGxy * sumGxy;

            if (trace > 0) {
                respRow[x] = static_cast<float>(det / trace);
            }
        }
    }

    return maskFromResponse(response, threshold);
}

// ============================================================================
// SUSAN — performance-critical: O(H*W*49) per-pixel loop
// ============================================================================

CornerResult detect_susan(const GrayImage& src, double t, double threshold) {
    validateGray(src);

    int rows = src.rows;
    int cols = src.cols;
    cv::Mat response(rows, cols, CV_32F, cv::Scalar(0));
    double maxResp = 0.0;

    // Circular mask radius 3 (37 pixels in 7x7 window)
    double tInv = 1.0 / t;

    for (int y = 3; y < rows - 3; ++y) {
        float* respRow = response.ptr<float>(y);

        for (int x = 3; x < cols - 3; ++x) {
            uchar center = src.at<uchar>(y, x);
            double similarity = 0.0;

            // 7x7 circular window — only points within radius 3.4
            for (int dy = -3; dy <= 3; ++dy) {
                const uchar* row = src.ptr<uchar>(y + dy);
                for (int dx = -3; dx <= 3; ++dx) {
                    double dist = std::sqrt(static_cast<double>(dx * dx + dy * dy));
                    if (dist > 3.4) continue;

                    double intensityDiff = static_cast<double>(row[x + dx]) - center;
                    double val = intensityDiff * tInv;
                    similarity += std::exp(-(val * val) * (val * val) * (val * val));
                }
            }

            // USAN area → corner response
            double geomThreshold = 0.75 * 37.0;
            double cornerResp = geomThreshold - similarity;
            if (cornerResp < 0) cornerResp = 0;

            respRow[x] = static_cast<float>(cornerResp);
            if (cornerResp > maxResp) maxResp = cornerResp;
        }
    }

    CornerResult cr;
    cr.mask = cv::Mat::zeros(rows, cols, CV_8UC1);
    if (maxResp <= 0) {
        cr.count = 0;
        return cr;
    }

    double thresh = maxResp * threshold;
    for (int y = 3; y < rows - 3; ++y) {
        uchar* maskRow = cr.mask.ptr<uchar>(y);
        float* respRow = response.ptr<float>(y);
        for (int x = 3; x < cols - 3; ++x) {
            if (respRow[x] > thresh) {
                maskRow[x] = 255;
            }
        }
    }

    simpleNMS(cr.mask);
    cr.count = cv::countNonZero(cr.mask);
    return cr;
}

// ============================================================================
// Rotate image
// ============================================================================

Image rotate_image(const Image& src, double angle, double scale, Interpolation interp) {
    if (src.empty())
        throw std::invalid_argument("Source image is empty");

    cv::Point2f center(src.cols / 2.0f, src.rows / 2.0f);
    cv::Mat M = cv::getRotationMatrix2D(center, angle, scale);

    int flags = cv::INTER_LINEAR;
    if (interp == Interpolation::NEAREST)  flags = cv::INTER_NEAREST;
    if (interp == Interpolation::BICUBIC)  flags = cv::INTER_CUBIC;

    cv::Mat dst;
    cv::warpAffine(src, dst, M, src.size(), flags);
    return dst;
}

// ============================================================================
// Draw corners
// ============================================================================

ColorImage draw_corners(const Image& src, const cv::Mat& mask, int pointSize, cv::Scalar color) {
    cv::Mat colorImg;
    if (src.channels() >= 3) {
        src.copyTo(colorImg);
    } else {
        cv::cvtColor(src, colorImg, cv::COLOR_GRAY2BGR);
    }

    int half = std::max(1, pointSize / 2);
    for (int y = 0; y < mask.rows; ++y) {
        const uchar* row = mask.ptr<uchar>(y);
        for (int x = 0; x < mask.cols; ++x) {
            if (row[x]) {
                cv::circle(colorImg, cv::Point(x, y), half, color, -1);
            }
        }
    }
    return colorImg;
}

} // namespace rstao
