#pragma once

#include <opencv2/core.hpp>
#include <opencv2/imgproc.hpp>
#include <opencv2/imgcodecs.hpp>

#include <string>
#include <vector>
#include <map>
#include <variant>
#include <cstdint>

namespace rstao {

// ---- Core type aliases ----

using Image     = cv::Mat;
using GrayImage = cv::Mat;   // CV_8UC1 expected
using ColorImage = cv::Mat;  // CV_8UC3 expected
using FloatImage = cv::Mat;  // CV_32F or CV_64F

// ---- Geo-transform (GDAL-style 6-element affine) ----

struct GeoTransform {
    double a[6] = {0.0, 1.0, 0.0, 0.0, 0.0, -1.0};
};

// ---- Raster metadata ----

struct RasterMetadata {
    int width = 0;
    int height = 0;
    int bands = 0;
    int dtype = 0;       // OpenCV Mat type constant, e.g. CV_8UC3
    std::string crs;     // empty when GDAL unavailable
    GeoTransform geotransform;
};

// ---- Processing result ----

using MetricValue = std::variant<int, double, std::string>;
using Metrics = std::map<std::string, MetricValue>;

struct ProcessingResult {
    Image image;
    Metrics metrics;
    Image display_image;  // optional — if empty, client uses `image`

    bool hasDisplayImage() const { return !display_image.empty(); }
};

// ---- Parameter value ----

using ParamValue = std::variant<int, double, std::string, bool>;
using ParamMap = std::map<std::string, ParamValue>;

// ---- Common enums ----

enum class Interpolation { NEAREST, BILINEAR, BICUBIC };

// ---- Helpers ----

inline int oddOrInt(int v) {
    return (v % 2 == 0) ? v + 1 : v;
}

inline cv::Mat toUint8(const cv::Mat& src) {
    if (src.depth() == CV_8U) return src;
    cv::Mat dst;
    src.convertTo(dst, CV_8U, 1.0, 0.0);
    return dst;
}

inline GrayImage toGray(const cv::Mat& src) {
    if (src.channels() == 1) return toUint8(src);
    cv::Mat gray;
    if (src.channels() >= 3) {
        cv::cvtColor(src, gray, cv::COLOR_BGR2GRAY);
    } else {
        gray = src;
    }
    return toUint8(gray);
}

inline cv::Mat to3Channel(const cv::Mat& src) {
    if (src.channels() == 3) return src;
    cv::Mat dst;
    cv::cvtColor(src, dst, cv::COLOR_GRAY2BGR);
    return dst;
}

} // namespace rstao
