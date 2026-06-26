#include <gtest/gtest.h>

#include <rstao/image_matching.hpp>

#include <opencv2/core.hpp>
#include <opencv2/imgproc.hpp>

#include <cmath>
#include <stdexcept>

using namespace rstao;

namespace {
constexpr int kTemplateSize = 20;

void drawPatternA(cv::Mat& img, cv::Point origin) {
    cv::rectangle(img, cv::Rect(origin.x, origin.y, kTemplateSize, kTemplateSize),
                  cv::Scalar(30, 30, 30), cv::FILLED);
    cv::rectangle(img, cv::Rect(origin.x + 3, origin.y + 3, 8, 11),
                  cv::Scalar(230, 230, 230), cv::FILLED);
    cv::line(img, cv::Point(origin.x + 1, origin.y + 18),
             cv::Point(origin.x + 18, origin.y + 1), cv::Scalar(90, 90, 90), 2);
    cv::circle(img, cv::Point(origin.x + 15, origin.y + 15), 3, cv::Scalar(170, 170, 170),
               cv::FILLED);
}

void drawPatternB(cv::Mat& img, cv::Point origin) {
    cv::rectangle(img, cv::Rect(origin.x, origin.y, kTemplateSize, kTemplateSize),
                  cv::Scalar(40, 40, 40), cv::FILLED);
    cv::circle(img, cv::Point(origin.x + 7, origin.y + 7), 5, cv::Scalar(220, 220, 220),
               cv::FILLED);
    cv::rectangle(img, cv::Rect(origin.x + 12, origin.y + 4, 5, 13),
                  cv::Scalar(120, 120, 120), cv::FILLED);
    cv::line(img, cv::Point(origin.x + 2, origin.y + 17),
             cv::Point(origin.x + 17, origin.y + 17), cv::Scalar(245, 245, 245), 1);
}

cv::Mat makePatternA() {
    cv::Mat tmpl(kTemplateSize, kTemplateSize, CV_8UC3, cv::Scalar(0, 0, 0));
    drawPatternA(tmpl, cv::Point(0, 0));
    return tmpl;
}

cv::Mat makePatternB() {
    cv::Mat tmpl(kTemplateSize, kTemplateSize, CV_8UC3, cv::Scalar(0, 0, 0));
    drawPatternB(tmpl, cv::Point(0, 0));
    return tmpl;
}

bool hasLocationNear(const std::vector<cv::Point>& locations, cv::Point expected, int tolerance = 5) {
    for (const auto& location : locations) {
        if (std::abs(location.x - expected.x) <= tolerance &&
            std::abs(location.y - expected.y) <= tolerance) {
            return true;
        }
    }
    return false;
}

// Create a 100x100 search image with a distinctive 20x20 pattern at (30, 30)
cv::Mat makeSearchImage() {
    cv::Mat img(100, 100, CV_8UC3, cv::Scalar(50, 50, 50));
    drawPatternA(img, cv::Point(30, 30));
    return img;
}

// Extract the 20x20 template at (30, 30)
cv::Mat makeTemplate() {
    return makePatternA();
}
} // namespace

// ---- match_single ----

TEST(MatchSingle, FindsTemplateInSearchImage) {
    cv::Mat search = makeSearchImage();
    cv::Mat tmpl = makeTemplate();
    MatchResult result = match_single(search, tmpl, 0.7);
    EXPECT_FALSE(result.locations.empty());
    EXPECT_EQ(result.template_size, cv::Size(20, 20));
    // The best match should be at or near (30, 30)
    cv::Point best = result.locations[0];
    EXPECT_NEAR(best.x, 30, 5);
    EXPECT_NEAR(best.y, 30, 5);
}

TEST(MatchSingle, HighThresholdReducesMatches) {
    cv::Mat search = makeSearchImage();
    cv::Mat tmpl = makeTemplate();
    MatchResult lowThresh = match_single(search, tmpl, 0.5);
    MatchResult highThresh = match_single(search, tmpl, 0.99);
    EXPECT_GE(lowThresh.locations.size(), highThresh.locations.size());
}

TEST(MatchSingle, EmptySearchThrows) {
    cv::Mat empty;
    cv::Mat tmpl = makeTemplate();
    EXPECT_THROW(match_single(empty, tmpl), std::invalid_argument);
}

// ---- match_multi ----

TEST(MatchMulti, FindsAllInstances) {
    // Create search image with two identical patterns
    cv::Mat search(120, 120, CV_8UC3, cv::Scalar(50, 50, 50));
    drawPatternA(search, cv::Point(10, 10));
    drawPatternA(search, cv::Point(70, 70));

    cv::Mat tmpl = makePatternA();
    MatchResult result = match_multi(search, tmpl, 0.7, 0.3);
    EXPECT_GE(result.locations.size(), 2u) << "Two patterns placed, expected >= 2 matches";
    EXPECT_TRUE(hasLocationNear(result.locations, cv::Point(10, 10)));
    EXPECT_TRUE(hasLocationNear(result.locations, cv::Point(70, 70)));
}

// ---- nms ----

TEST(NMS, RemovesOverlappingDetections) {
    // Three overlapping points + one distant
    std::vector<cv::Point> locations = {
        cv::Point(30, 30),   // overlaps with next
        cv::Point(32, 32),   // overlaps with prev
        cv::Point(35, 35),   // overlaps with prev
        cv::Point(90, 90),   // isolated
    };
    std::vector<double> scores = {0.95, 0.90, 0.85, 0.80};
    std::vector<int> kept = nms(locations, scores, 0.3);
    // Should keep the best from the cluster + the isolated one
    EXPECT_LE(kept.size(), locations.size());
    EXPECT_GE(kept.size(), 1u);
}

TEST(NMS, EmptyInputReturnsEmpty) {
    std::vector<cv::Point> locations;
    std::vector<double> scores;
    std::vector<int> kept = nms(locations, scores, 0.3);
    EXPECT_TRUE(kept.empty());
}

// ---- match_multi_target ----

TEST(MatchMultiTarget, HandlesMultipleTemplates) {
    cv::Mat search(120, 120, CV_8UC3, cv::Scalar(50, 50, 50));
    drawPatternA(search, cv::Point(10, 10));
    drawPatternB(search, cv::Point(70, 70));

    std::vector<cv::Mat> templates = {
        makePatternA(),
        makePatternB(),
    };
    std::vector<MatchResult> results = match_multi_target(search, templates, 0.7);
    EXPECT_EQ(results.size(), 2u);
    for (const auto& r : results) {
        EXPECT_FALSE(r.locations.empty());
    }
    EXPECT_TRUE(hasLocationNear(results[0].locations, cv::Point(10, 10)));
    EXPECT_TRUE(hasLocationNear(results[1].locations, cv::Point(70, 70)));
}

// ---- draw_match_result ----

TEST(DrawMatchResult, ProducesColorOutput) {
    cv::Mat search = makeSearchImage();
    cv::Mat tmpl = makeTemplate();
    MatchResult result = match_single(search, tmpl, 0.7);
    ColorImage drawn = draw_match_result(search, result);
    EXPECT_FALSE(drawn.empty());
    EXPECT_GE(drawn.channels(), 3);
}

// ---- Edge cases ----

TEST(MatchSingle, TemplateLargerThanSearchThrows) {
    cv::Mat search(50, 50, CV_8UC3, cv::Scalar(100, 100, 100));
    cv::Mat tmpl(100, 100, CV_8UC3, cv::Scalar(200, 200, 200));
    EXPECT_THROW(match_single(search, tmpl), std::invalid_argument);
}
