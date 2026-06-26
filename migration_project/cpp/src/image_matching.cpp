#include "rstao/image_matching.hpp"

#include <opencv2/imgproc.hpp>

#include <cmath>
#include <stdexcept>
#include <algorithm>
#include <numeric>

namespace rstao {

namespace {

void validate(const cv::Mat& search, const cv::Mat& templ) {
    if (search.empty()) throw std::invalid_argument("Search image is empty");
    if (templ.empty())  throw std::invalid_argument("Template image is empty");
    if (templ.cols > search.cols || templ.rows > search.rows)
        throw std::invalid_argument("Template is larger than search image");
}

// Extract peaks above threshold from correlation map
std::vector<cv::Point> extractPeaks(const cv::Mat& corrMap, double threshold,
                                     std::vector<double>* outScores = nullptr,
                                     int maxCount = 0) {
    std::vector<cv::Point> pts;
    double minVal, maxVal;
    cv::minMaxLoc(corrMap, &minVal, &maxVal);
    double thresh = minVal + (maxVal - minVal) * threshold;

    for (int y = 0; y < corrMap.rows; ++y) {
        const float* row = corrMap.ptr<float>(y);
        for (int x = 0; x < corrMap.cols; ++x) {
            if (row[x] > thresh) {
                pts.push_back(cv::Point(x, y));
                if (outScores) outScores->push_back(row[x]);
            }
        }
    }

    if (maxCount > 0 && static_cast<int>(pts.size()) > maxCount) {
        // Keep top maxCount by score
        std::vector<int> indices(pts.size());
        std::iota(indices.begin(), indices.end(), 0);
        std::sort(indices.begin(), indices.end(), [&](int a, int b) {
            return (*outScores)[a] > (*outScores)[b];
        });
        indices.resize(maxCount);
        std::vector<cv::Point> filteredPts;
        std::vector<double> filteredScores;
        for (int idx : indices) {
            filteredPts.push_back(pts[idx]);
            if (outScores) filteredScores.push_back((*outScores)[idx]);
        }
        pts = filteredPts;
        if (outScores) *outScores = filteredScores;
    }
    return pts;
}

} // anonymous namespace

// ============================================================================
// Single template matching (best match only)
// ============================================================================

MatchResult match_single(const Image& search, const Image& templ, double threshold) {
    validate(search, templ);

    cv::Mat searchGray = (search.channels() >= 3) ? cv::Mat() : search;
    cv::Mat templGray  = (templ.channels() >= 3)  ? cv::Mat() : templ;

    if (search.channels() >= 3) cv::cvtColor(search, searchGray, cv::COLOR_BGR2GRAY);
    if (templ.channels() >= 3)  cv::cvtColor(templ,  templGray,  cv::COLOR_BGR2GRAY);

    cv::Mat corrMap;
    cv::matchTemplate(searchGray, templGray, corrMap, cv::TM_CCOEFF_NORMED);

    double minVal, maxVal;
    cv::Point minLoc, maxLoc;
    cv::minMaxLoc(corrMap, &minVal, &maxVal, &minLoc, &maxLoc);

    MatchResult result;
    result.template_size = templ.size();
    if (maxVal >= threshold) {
        result.locations = {maxLoc};
        result.scores    = {maxVal};
    }
    return result;
}

// ============================================================================
// Multi-object matching (all peaks above threshold, with NMS)
// ============================================================================

MatchResult match_multi(const Image& search, const Image& templ,
                        double threshold, double nmsThreshold) {
    validate(search, templ);

    cv::Mat searchGray = (search.channels() >= 3) ? cv::Mat() : search;
    cv::Mat templGray  = (templ.channels() >= 3)  ? cv::Mat() : templ;

    if (search.channels() >= 3) cv::cvtColor(search, searchGray, cv::COLOR_BGR2GRAY);
    if (templ.channels() >= 3)  cv::cvtColor(templ,  templGray,  cv::COLOR_BGR2GRAY);

    cv::Mat corrMap;
    cv::matchTemplate(searchGray, templGray, corrMap, cv::TM_CCOEFF_NORMED);

    std::vector<double> scores;
    auto locations = extractPeaks(corrMap, threshold, &scores);

    MatchResult result;
    result.template_size = templ.size();

    if (!locations.empty()) {
        auto keep = nms(locations, scores, nmsThreshold);
        for (int idx : keep) {
            result.locations.push_back(locations[idx]);
            result.scores.push_back(scores[idx]);
        }
    }
    return result;
}

// ============================================================================
// Multi-target matching
// ============================================================================

std::vector<MatchResult> match_multi_target(const Image& search,
                                            const std::vector<Image>& templates,
                                            double threshold) {
    std::vector<MatchResult> results;
    results.reserve(templates.size());
    for (const auto& tpl : templates) {
        results.push_back(match_multi(search, tpl, threshold));
    }
    return results;
}

// ============================================================================
// Non-Maximum Suppression
// ============================================================================

std::vector<int> nms(const std::vector<cv::Point>& locations,
                     const std::vector<double>& scores,
                     double threshold) {
    std::vector<int> keep;
    int n = static_cast<int>(locations.size());
    if (n == 0) return keep;

    // Sort indices by score descending
    std::vector<int> indices(n);
    std::iota(indices.begin(), indices.end(), 0);
    std::sort(indices.begin(), indices.end(), [&](int a, int b) {
        return scores[a] > scores[b];
    });

    std::vector<bool> suppressed(n, false);
    double threshSq = threshold * threshold;

    for (int i = 0; i < n; ++i) {
        int ii = indices[i];
        if (suppressed[ii]) continue;
        keep.push_back(ii);

        for (int j = i + 1; j < n; ++j) {
            int jj = indices[j];
            if (suppressed[jj]) continue;
            double dx = locations[ii].x - locations[jj].x;
            double dy = locations[ii].y - locations[jj].y;
            if (dx * dx + dy * dy < threshSq) {
                suppressed[jj] = true;
            }
        }
    }
    return keep;
}

// ============================================================================
// Draw match results
// ============================================================================

ColorImage draw_match_result(const ColorImage& search, const MatchResult& result, cv::Scalar color) {
    cv::Mat out;
    search.copyTo(out);
    if (out.channels() == 1)
        cv::cvtColor(out, out, cv::COLOR_GRAY2BGR);

    int tw = result.template_size.width;
    int th = result.template_size.height;

    for (size_t i = 0; i < result.locations.size(); ++i) {
        cv::Point pt = result.locations[i];
        cv::rectangle(out, cv::Rect(pt.x, pt.y, tw, th), color, 2);

        // Score label
        char buf[32];
        std::snprintf(buf, sizeof(buf), "%.2f", result.scores[i]);
        cv::putText(out, buf, cv::Point(pt.x, pt.y - 6),
                    cv::FONT_HERSHEY_SIMPLEX, 0.45, color, 1);
    }
    return out;
}

// ============================================================================
// Draw heatmap
// ============================================================================

ColorImage draw_heatmap(const Image& search, const std::vector<cv::Point>& locations,
                        const std::vector<double>& scores) {
    cv::Mat heatmap(search.size(), CV_32F, cv::Scalar(0));
    double maxScore = 1.0;
    if (!scores.empty()) {
        maxScore = *std::max_element(scores.begin(), scores.end());
    }

    for (size_t i = 0; i < locations.size(); ++i) {
        cv::Point pt = locations[i];
        if (pt.x >= 0 && pt.x < heatmap.cols && pt.y >= 0 && pt.y < heatmap.rows) {
            heatmap.at<float>(pt.y, pt.x) = static_cast<float>(scores[i] / maxScore);
        }
    }

    // Gaussian blur for smoother heatmap
    cv::GaussianBlur(heatmap, heatmap, cv::Size(21, 21), 0);

    // Color map
    cv::Mat colorMap;
    heatmap.convertTo(heatmap, CV_8U, 255.0);
    cv::applyColorMap(heatmap, colorMap, cv::COLORMAP_JET);

    // Blend with original
    cv::Mat base;
    if (search.channels() == 1) {
        cv::cvtColor(search, base, cv::COLOR_GRAY2BGR);
    } else {
        search.copyTo(base);
    }
    cv::Mat blended;
    cv::addWeighted(base, 0.5, colorMap, 0.5, 0, blended);
    return blended;
}

} // namespace rstao
