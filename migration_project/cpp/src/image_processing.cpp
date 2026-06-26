#include "rstao/image_processing.hpp"

#include <opencv2/imgproc.hpp>
#include <opencv2/highgui.hpp>

#include <cmath>
#include <stdexcept>
#include <algorithm>
#include <numeric>
#include <string>
#include <map>
#include <functional>

namespace rstao {

namespace {

// ---- Internal helpers ----

void validateNonEmpty(const cv::Mat& src, const char* name) {
    if (src.empty())
        throw std::invalid_argument(std::string(name) + " image is empty");
}

GrayImage ensureGray(const cv::Mat& src) {
    validateNonEmpty(src, "Source");
    return toGray(src);
}

cv::Mat ensureColor(const cv::Mat& src) {
    validateNonEmpty(src, "Source");
    if (src.channels() >= 3)
        return src;
    cv::Mat dst;
    cv::cvtColor(src, dst, cv::COLOR_GRAY2BGR);
    return dst;
}

// Percentile stretch per band, returns CV_8U
cv::Mat percentileStretch(const cv::Mat& src, double lowPct, double highPct) {
    cv::Mat result;
    if (src.channels() == 1) {
        cv::Mat flat;
        src.reshape(1, 1).copyTo(flat);
        if (flat.depth() != CV_8U) {
            cv::Mat tmp;
            flat.convertTo(tmp, CV_32F);
            flat = tmp;
        }
        cv::Mat sorted;
        cv::sort(flat, sorted, cv::SORT_EVERY_ROW + cv::SORT_ASCENDING);
        int total = sorted.cols;
        double lowVal, highVal;
        if (sorted.depth() == CV_8U) {
            lowVal  = sorted.at<uchar>(0, static_cast<int>(total * lowPct  / 100.0));
            highVal = sorted.at<uchar>(0, static_cast<int>(total * highPct / 100.0));
        } else {
            lowVal  = sorted.at<float>(0, static_cast<int>(total * lowPct  / 100.0));
            highVal = sorted.at<float>(0, static_cast<int>(total * highPct / 100.0));
        }
        double range = highVal - lowVal;
        if (range <= 0.0) range = 1.0;
        cv::Mat stretched;
        src.convertTo(stretched, CV_32F);
        stretched = (stretched - lowVal) / range * 255.0;
        stretched.setTo(0, stretched < 0);
        stretched.setTo(255, stretched > 255);
        stretched.convertTo(result, CV_8U);
    } else {
        std::vector<cv::Mat> channels;
        cv::split(src, channels);
        std::vector<cv::Mat> dstChannels;
        for (const auto& ch : channels) {
            dstChannels.push_back(percentileStretch(ch, lowPct, highPct));
        }
        cv::merge(dstChannels, result);
    }
    return result;
}

// Basic metrics for a result image
Metrics basicMetrics(const cv::Mat& img) {
    Metrics m;
    m["dtype"]   = img.depth();
    m["channels"] = img.channels();
    m["width"]   = img.cols;
    m["height"]  = img.rows;
    return m;
}

// Helper: get param value or default
std::string paramStr(const ParamMap& p, const std::string& key, const std::string& def = "") {
    auto it = p.find(key);
    if (it == p.end()) return def;
    if (auto* s = std::get_if<std::string>(&it->second)) return *s;
    return def;
}

int paramInt(const ParamMap& p, const std::string& key, int def = 0) {
    auto it = p.find(key);
    if (it == p.end()) return def;
    if (auto* v = std::get_if<int>(&it->second)) return *v;
    if (auto* v = std::get_if<double>(&it->second)) return static_cast<int>(*v);
    return def;
}

double paramDouble(const ParamMap& p, const std::string& key, double def = 0.0) {
    auto it = p.find(key);
    if (it == p.end()) return def;
    if (auto* v = std::get_if<double>(&it->second)) return *v;
    if (auto* v = std::get_if<int>(&it->second)) return static_cast<double>(*v);
    return def;
}

bool paramBool(const ParamMap& p, const std::string& key, bool def = false) {
    auto it = p.find(key);
    if (it == p.end()) return def;
    if (auto* v = std::get_if<bool>(&it->second)) return *v;
    return def;
}

} // anonymous namespace

// ============================================================================
// Public operator implementations
// ============================================================================

Image to_grayscale(const Image& src) {
    cv::Mat gray = ensureGray(src);
    return gray;
}

Image convert_color_space(const Image& src, const std::string& target) {
    cv::Mat rgb = ensureColor(src);
    cv::Mat out;
    if (target == "HSV") {
        cv::cvtColor(rgb, out, cv::COLOR_BGR2HSV);
    } else if (target == "HLS") {
        cv::cvtColor(rgb, out, cv::COLOR_BGR2HLS);
    } else if (target == "Lab") {
        cv::cvtColor(rgb, out, cv::COLOR_BGR2Lab);
    } else if (target == "YCrCb") {
        cv::cvtColor(rgb, out, cv::COLOR_BGR2YCrCb);
    } else {
        // GRAY or unknown fallback
        cv::cvtColor(rgb, out, cv::COLOR_BGR2GRAY);
    }
    return out;
}

Image linear_stretch(const Image& src, double lowPct, double highPct) {
    validateNonEmpty(src, "Source");
    return percentileStretch(src, lowPct, highPct);
}

Image histogram_equalize(const Image& src) {
    cv::Mat gray = ensureGray(src);
    cv::Mat out;
    cv::equalizeHist(gray, out);
    return out;
}

Image match_histogram(const Image& source, const Image& reference) {
    validateNonEmpty(source, "Source");
    validateNonEmpty(reference, "Reference");
    cv::Mat srcGray = ensureGray(source);
    cv::Mat refGray = ensureGray(reference);

    // Compute CDF of source
    int histSize = 256;
    float range[] = {0, 256};
    const float* histRange = {range};
    cv::Mat srcHist, refHist;
    cv::calcHist(&srcGray, 1, nullptr, cv::Mat(), srcHist, 1, &histSize, &histRange);
    cv::calcHist(&refGray, 1, nullptr, cv::Mat(), refHist, 1, &histSize, &histRange);

    // Cumulative
    for (int i = 1; i < 256; ++i) {
        srcHist.at<float>(i) += srcHist.at<float>(i - 1);
        refHist.at<float>(i) += refHist.at<float>(i - 1);
    }
    // Normalize
    float srcTotal = srcHist.at<float>(255);
    float refTotal = refHist.at<float>(255);
    if (srcTotal <= 0 || refTotal <= 0) return srcGray.clone();

    // Build LUT
    uchar lut[256] = {0};
    for (int i = 0; i < 256; ++i) {
        float srcVal = srcHist.at<float>(i) / srcTotal;
        int j = 0;
        while (j < 255 && refHist.at<float>(j) / refTotal < srcVal) ++j;
        lut[i] = static_cast<uchar>(j);
    }

    cv::Mat out;
    cv::LUT(srcGray, cv::Mat(1, 256, CV_8U, lut), out);
    return out;
}

Image smooth(const Image& src, const std::string& method, int ksize) {
    cv::Mat input = ensureColor(src);
    int k = oddOrInt(std::max(3, ksize));
    cv::Mat out;
    if (method == "gaussian") {
        cv::GaussianBlur(input, out, cv::Size(k, k), 0);
    } else if (method == "median") {
        cv::medianBlur(input, out, k);
    } else if (method == "bilateral") {
        cv::bilateralFilter(input, out, k, k * 2.0, k / 2.0);
    } else {
        // default: box/average
        cv::blur(input, out, cv::Size(k, k));
    }
    return out;
}

Image sharpen(const Image& src, const std::string& method, double amount) {
    cv::Mat input = ensureColor(src);
    cv::Mat out;
    if (method == "laplacian") {
        cv::Mat laplacian;
        cv::Laplacian(input, laplacian, CV_16S, 3);
        cv::Mat laplacianF;
        laplacian.convertTo(laplacianF, CV_32F);
        cv::Mat inputF;
        input.convertTo(inputF, CV_32F);
        cv::Mat sharp = inputF - amount * laplacianF;
        sharp.setTo(0, sharp < 0);
        sharp.setTo(255, sharp > 255);
        sharp.convertTo(out, CV_8U);
    } else {
        // unsharp_mask
        cv::Mat blurred;
        cv::GaussianBlur(input, blurred, cv::Size(0, 0), 3.0);
        cv::addWeighted(input, 1.0 + amount, blurred, -amount, 0, out);
    }
    return out;
}

Image edge_detect(const Image& src, const std::string& mode) {
    cv::Mat gray = ensureGray(src);
    cv::Mat out;

    if (mode == "sobel") {
        cv::Mat gx, gy;
        cv::Sobel(gray, gx, CV_32F, 1, 0, 3);
        cv::Sobel(gray, gy, CV_32F, 0, 1, 3);
        cv::Mat mag;
        cv::magnitude(gx, gy, mag);
        mag = percentileStretch(mag, 2.0, 98.0);
        return mag;
    }
    if (mode == "laplacian") {
        cv::Laplacian(gray, out, CV_32F, 3);
        cv::convertScaleAbs(out, out);
        return out;
    }
    if (mode == "canny") {
        cv::Canny(gray, out, 50, 150, 3);
        return out;
    }
    if (mode == "direction") {
        cv::Mat gx, gy;
        cv::Sobel(gray, gx, CV_32F, 1, 0, 3);
        cv::Sobel(gray, gy, CV_32F, 0, 1, 3);
        cv::Mat angle;
        cv::phase(gx, gy, angle, true); // degrees
        angle.convertTo(out, CV_8U, 255.0 / 360.0);
        return out;
    }
    // "magnitude" default
    cv::Mat gx, gy;
    cv::Sobel(gray, gx, CV_32F, 1, 0, 3);
    cv::Sobel(gray, gy, CV_32F, 0, 1, 3);
    cv::Mat mag;
    cv::magnitude(gx, gy, mag);
    mag = percentileStretch(mag, 2.0, 98.0);
    return mag;
}

Image morphology(const Image& src, const std::string& operation, int ksize, int iterations) {
    cv::Mat input = toUint8(src);
    int k = oddOrInt(std::max(3, ksize));
    int it = std::max(1, iterations);
    cv::Mat kernel = cv::getStructuringElement(cv::MORPH_ELLIPSE, cv::Size(k, k));
    cv::Mat out;

    if (operation == "erode") {
        cv::erode(input, out, kernel, cv::Point(-1, -1), it);
    } else if (operation == "dilate") {
        cv::dilate(input, out, kernel, cv::Point(-1, -1), it);
    } else if (operation == "open") {
        cv::morphologyEx(input, out, cv::MORPH_OPEN, kernel, cv::Point(-1, -1), it);
    } else if (operation == "close") {
        cv::morphologyEx(input, out, cv::MORPH_CLOSE, kernel, cv::Point(-1, -1), it);
    } else if (operation == "gradient") {
        cv::morphologyEx(input, out, cv::MORPH_GRADIENT, kernel, cv::Point(-1, -1), it);
    } else if (operation == "tophat") {
        cv::morphologyEx(input, out, cv::MORPH_TOPHAT, kernel, cv::Point(-1, -1), it);
    } else if (operation == "blackhat") {
        cv::morphologyEx(input, out, cv::MORPH_BLACKHAT, kernel, cv::Point(-1, -1), it);
    } else {
        out = input;
    }
    return out;
}

Image threshold_binary(const Image& src, const std::string& method, double value, int blockSize) {
    cv::Mat gray = ensureGray(src);
    cv::Mat out;

    if (method == "otsu") {
        cv::threshold(gray, out, 0, 255, cv::THRESH_BINARY | cv::THRESH_OTSU);
    } else if (method == "adaptive_mean") {
        int b = oddOrInt(std::max(3, blockSize));
        cv::adaptiveThreshold(gray, out, 255, cv::ADAPTIVE_THRESH_MEAN_C, cv::THRESH_BINARY, b, 5);
    } else if (method == "adaptive_gaussian") {
        int b = oddOrInt(std::max(3, blockSize));
        cv::adaptiveThreshold(gray, out, 255, cv::ADAPTIVE_THRESH_GAUSSIAN_C, cv::THRESH_BINARY, b, 5);
    } else {
        // manual
        cv::threshold(gray, out, value, 255, cv::THRESH_BINARY);
    }
    return out;
}

Image pca_component(const Image& src, int componentIdx) {
    validateNonEmpty(src, "Source");
    if (src.channels() == 1) {
        return percentileStretch(src, 2.0, 98.0);
    }

    int bands = src.channels();
    int ci = std::max(0, std::min(componentIdx, bands - 1));

    // Build (N, bands) data matrix for PCA
    int total = src.rows * src.cols;
    cv::Mat data(total, bands, CV_64F);
    if (bands == 3) {
        for (int r = 0; r < src.rows; ++r) {
            const cv::Vec3b* row = src.ptr<cv::Vec3b>(r);
            int base = r * src.cols;
            for (int c = 0; c < src.cols; ++c) {
                data.at<double>(base + c, 0) = row[c][0];
                data.at<double>(base + c, 1) = row[c][1];
                data.at<double>(base + c, 2) = row[c][2];
            }
        }
    } else {
        for (int r = 0; r < src.rows; ++r) {
            const uchar* row = src.ptr<uchar>(r);
            int base = r * src.cols;
            for (int c = 0; c < src.cols; ++c) {
                for (int b = 0; b < bands; ++b) {
                    data.at<double>(base + c, b) = row[c * bands + b];
                }
            }
        }
    }

    // PCA via OpenCV
    cv::PCA pca(data, cv::Mat(), cv::PCA::DATA_AS_ROW, bands);
    cv::Mat projected = pca.project(data);

    // Extract one component — col() returns non-contiguous, clone for reshape
    cv::Mat comp = projected.col(ci).clone().reshape(1, src.rows);
    return percentileStretch(comp, 2.0, 98.0);
}

Image ihs_intensity(const Image& src) {
    cv::Mat rgb = ensureColor(src);
    cv::Mat hsv;
    cv::cvtColor(rgb, hsv, cv::COLOR_BGR2HSV);
    // Intensity = V channel
    cv::Mat intensity;
    cv::extractChannel(hsv, intensity, 2);
    return intensity;
}

Image fft_filter(const Image& src, const std::string& mode, double radius) {
    cv::Mat gray = ensureGray(src);
    cv::Mat floatImg;
    gray.convertTo(floatImg, CV_32F);

    // Optimal DFT size
    int m = cv::getOptimalDFTSize(gray.rows);
    int n = cv::getOptimalDFTSize(gray.cols);
    cv::Mat padded;
    cv::copyMakeBorder(floatImg, padded, 0, m - gray.rows, 0, n - gray.cols,
                       cv::BORDER_CONSTANT, cv::Scalar::all(0));

    // DFT
    cv::Mat planes[] = {padded, cv::Mat::zeros(padded.size(), CV_32F)};
    cv::Mat complex;
    cv::merge(planes, 2, complex);
    cv::dft(complex, complex);

    // Shift
    int cx = complex.cols / 2;
    int cy = complex.rows / 2;
    cv::Mat q0(complex, cv::Rect(0, 0, cx, cy));
    cv::Mat q1(complex, cv::Rect(cx, 0, cx, cy));
    cv::Mat q2(complex, cv::Rect(0, cy, cx, cy));
    cv::Mat q3(complex, cv::Rect(cx, cy, cx, cy));
    cv::Mat tmp;
    q0.copyTo(tmp); q3.copyTo(q0); tmp.copyTo(q3);
    q1.copyTo(tmp); q2.copyTo(q1); tmp.copyTo(q2);

    // Create mask
    cv::Mat mask(complex.size(), CV_32F, cv::Scalar(0));
    cv::circle(mask, cv::Point(cx, cy), static_cast<int>(radius), cv::Scalar(1), -1);
    if (mode == "highpass")
        mask = cv::Scalar(1) - mask;

    // Apply
    cv::Mat maskMerged[2] = {mask, mask};
    cv::Mat maskComplex;
    cv::merge(maskMerged, 2, maskComplex);
    cv::multiply(complex, maskComplex, complex);

    // Inverse shift
    q0.copyTo(tmp); q3.copyTo(q0); tmp.copyTo(q3);
    q1.copyTo(tmp); q2.copyTo(q1); tmp.copyTo(q2);

    // IDFT
    cv::Mat inverse;
    cv::idft(complex, inverse, cv::DFT_SCALE | cv::DFT_REAL_OUTPUT);

    cv::Mat result = inverse(cv::Rect(0, 0, gray.cols, gray.rows));
    return percentileStretch(result, 2.0, 98.0);
}

Image normalized_difference(const Image& src, int bandA, int bandB) {
    validateNonEmpty(src, "Source");
    if (src.channels() < 2)
        throw std::invalid_argument("normalized_difference requires at least 2 bands");

    int ba = std::max(0, std::min(bandA, src.channels() - 1));
    int bb = std::max(0, std::min(bandB, src.channels() - 1));

    std::vector<cv::Mat> channels;
    cv::split(src, channels);

    cv::Mat a, b;
    channels[ba].convertTo(a, CV_32F);
    channels[bb].convertTo(b, CV_32F);

    cv::Mat num = a - b;
    cv::Mat denom = a + b + 1e-6f;
    cv::Mat nd;
    cv::divide(num, denom, nd);

    return percentileStretch(nd, 2.0, 98.0);
}

// ---- Display helpers ----

Image display_preview(const Image& src, double lowPct, double highPct) {
    validateNonEmpty(src, "Source");
    return percentileStretch(src, lowPct, highPct);
}

// ---- Unified dispatch ----

namespace {

// Forward callback helper through a per-operator call.
// When progress is null, operators skip progress reporting (existing behavior).
Image dispatchProcess(const Image& image, const std::string& opId,
                      const ParamMap& params, ProgressCallback progress) {
    auto callProgress = [&](int p) { if (progress) progress(p); };
    callProgress(0);
    Image result;

    if (opId == "grayscale") {
        callProgress(50);
        result = to_grayscale(image);
        callProgress(100);
    } else if (opId == "color_space") {
        callProgress(30);
        result = convert_color_space(image, paramStr(params, "target", "HSV"));
        callProgress(100);
    } else if (opId == "linear_stretch") {
        callProgress(25);
        result = linear_stretch(image, paramDouble(params, "low_percent", 2.0),
                                         paramDouble(params, "high_percent", 98.0));
        callProgress(100);
    } else if (opId == "histogram_equalization") {
        callProgress(50);
        result = histogram_equalize(image);
        callProgress(100);
    } else if (opId == "histogram_match") {
        throw std::invalid_argument("histogram_match requires reference image, use match_histogram() directly");
    } else if (opId == "smooth") {
        callProgress(30);
        result = smooth(image, paramStr(params, "method", "gaussian"),
                                paramInt(params, "ksize", 5));
        callProgress(100);
    } else if (opId == "sharpen") {
        callProgress(30);
        result = sharpen(image, paramStr(params, "method", "unsharp_mask"),
                                  paramDouble(params, "amount", 1.0));
        callProgress(100);
    } else if (opId == "edge_detect") {
        callProgress(25);
        result = edge_detect(image, paramStr(params, "mode", "magnitude"));
        callProgress(100);
    } else if (opId == "morphology") {
        callProgress(30);
        result = morphology(image, paramStr(params, "operation", "erode"),
                                     paramInt(params, "ksize", 3),
                                     paramInt(params, "iterations", 1));
        callProgress(100);
    } else if (opId == "threshold") {
        callProgress(30);
        result = threshold_binary(image, paramStr(params, "method", "otsu"),
                                           paramDouble(params, "threshold", 127),
                                           paramInt(params, "block_size", 11));
        callProgress(100);
    } else if (opId == "pca") {
        callProgress(50);
        result = pca_component(image, paramInt(params, "component", 1) - 1);
        callProgress(100);
    } else if (opId == "ihs_intensity") {
        callProgress(50);
        result = ihs_intensity(image);
        callProgress(100);
    } else if (opId == "fft_filter") {
        callProgress(40);
        result = fft_filter(image, paramStr(params, "mode", "lowpass"),
                                     paramDouble(params, "radius", 30.0));
        callProgress(70);
        callProgress(100);
    } else if (opId == "normalized_difference") {
        callProgress(50);
        result = normalized_difference(image, paramInt(params, "band_a", 1) - 1,
                                                paramInt(params, "band_b", 2) - 1);
        callProgress(100);
    } else {
        throw std::invalid_argument("Unknown operator: " + opId);
    }
    return result;
}

} // anonymous namespace

ProcessingResult process(const Image& image, const std::string& opId, const ParamMap& params) {
    if (image.empty())
        throw std::invalid_argument("Input image is empty");

    Image result = dispatchProcess(image, opId, params, nullptr);

    Metrics metrics = basicMetrics(result);
    metrics["operator_id"] = opId;
    return ProcessingResult{result, metrics, Image()};
}

ProcessingResult process(const Image& image, const std::string& opId,
                         const ParamMap& params, ProgressCallback progress) {
    if (image.empty())
        throw std::invalid_argument("Input image is empty");

    Image result = dispatchProcess(image, opId, params, progress);

    Metrics metrics = basicMetrics(result);
    metrics["operator_id"] = opId;
    return ProcessingResult{result, metrics, Image()};
}

} // namespace rstao
