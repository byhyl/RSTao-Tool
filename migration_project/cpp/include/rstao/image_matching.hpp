#pragma once

#include "rstao/common/types.hpp"

#include <opencv2/core.hpp>

namespace rstao {

struct MatchResult {
    std::vector<cv::Point> locations;
    std::vector<double> scores;
    cv::Size template_size;
};

// ---- Template matching ----

MatchResult match_single(const Image& search, const Image& templ, double threshold = 0.7);

MatchResult match_multi(const Image& search, const Image& templ,
                        double threshold = 0.7, double nms_threshold = 0.3);

std::vector<MatchResult> match_multi_target(const Image& search,
                                            const std::vector<Image>& templates,
                                            double threshold = 0.7);

// ---- Non-maximum suppression ----

std::vector<int> nms(const std::vector<cv::Point>& locations,
                     const std::vector<double>& scores,
                     double threshold);

// ---- Drawing ----

ColorImage draw_match_result(const ColorImage& search, const MatchResult& result,
                             cv::Scalar color = {0, 255, 0});

ColorImage draw_heatmap(const Image& search, const std::vector<cv::Point>& locations,
                        const std::vector<double>& scores);

} // namespace rstao
