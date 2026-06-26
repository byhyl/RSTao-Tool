#pragma once

#include "rstao/common/types.hpp"

namespace rstao {

struct CornerResult {
    cv::Mat mask;   // CV_8UC1, 255 = corner
    int count = 0;
};

// ---- Corner detectors ----

CornerResult detect_harris(const GrayImage& src, double k = 0.04, double threshold = 0.01);

CornerResult detect_moravec(const GrayImage& src, double threshold = 0.01);

CornerResult detect_forstner(const GrayImage& src, double threshold = 0.01);

CornerResult detect_susan(const GrayImage& src, double t = 27.0, double threshold = 0.01);

// ---- Utility ----

Image rotate_image(const Image& src, double angle, double scale = 1.0,
                   Interpolation interp = Interpolation::BILINEAR);

ColorImage draw_corners(const Image& src, const cv::Mat& mask, int point_size = 3,
                        cv::Scalar color = {0, 255, 0});

} // namespace rstao
