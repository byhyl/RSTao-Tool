#include <gtest/gtest.h>
#include <rstao/feature_detection.hpp>

#include <opencv2/imgproc.hpp>

using namespace rstao;

namespace {

class FeatureDetectionTest : public ::testing::Test {
protected:
    void SetUp() override {
        // 128x128 gray image with a high-contrast square in center
        gray = cv::Mat(128, 128, CV_8UC1, cv::Scalar(128));
        cv::rectangle(gray, cv::Rect(44, 44, 40, 40), cv::Scalar(255), -1);
    }

    cv::Mat gray;
    cv::Mat empty;
};

TEST_F(FeatureDetectionTest, HarrisReturnsMaskAndCount) {
    CornerResult r = detect_harris(gray, 0.04, 0.01);
    EXPECT_FALSE(r.mask.empty());
    EXPECT_EQ(r.mask.size(), gray.size());
    EXPECT_EQ(r.mask.depth(), CV_8U);
    EXPECT_GE(r.count, 0);
    // Square corners should produce some detections
    EXPECT_GT(r.count, 0);
}

TEST_F(FeatureDetectionTest, MoravecReturnsMaskAndCount) {
    CornerResult r = detect_moravec(gray, 0.01);
    EXPECT_FALSE(r.mask.empty());
    EXPECT_EQ(r.mask.size(), gray.size());
    EXPECT_GT(r.count, 0);
}

TEST_F(FeatureDetectionTest, ForstnerReturnsMaskAndCount) {
    CornerResult r = detect_forstner(gray, 0.01);
    EXPECT_FALSE(r.mask.empty());
    EXPECT_EQ(r.mask.size(), gray.size());
    EXPECT_GT(r.count, 0);
}

TEST_F(FeatureDetectionTest, SusanReturnsMaskAndCount) {
    CornerResult r = detect_susan(gray, 27.0, 0.01);
    EXPECT_FALSE(r.mask.empty());
    EXPECT_EQ(r.mask.size(), gray.size());
    // SUSAN on this image should find corners of the square
    EXPECT_GT(r.count, 0);
}

TEST_F(FeatureDetectionTest, CornerCountsAreConsistent) {
    CornerResult harris   = detect_harris(gray, 0.04, 0.01);
    CornerResult moravec  = detect_moravec(gray, 0.01);
    CornerResult forstner = detect_forstner(gray, 0.01);

    // All detectors should find at least some corners
    EXPECT_GT(harris.count, 0);
    EXPECT_GT(moravec.count, 0);
    EXPECT_GT(forstner.count, 0);

    // Masks are binary
    double minVal, maxVal;
    cv::minMaxLoc(harris.mask, &minVal, &maxVal);
    EXPECT_EQ(minVal, 0);
    EXPECT_EQ(maxVal, 255);
}

TEST_F(FeatureDetectionTest, RotateImage) {
    cv::Mat rotated = rotate_image(gray, 45.0, 1.0, Interpolation::BILINEAR);
    EXPECT_EQ(rotated.size(), gray.size());
}

TEST_F(FeatureDetectionTest, RotateImageWithScale) {
    cv::Mat rotated = rotate_image(gray, 90.0, 0.5, Interpolation::NEAREST);
    EXPECT_EQ(rotated.size(), gray.size());
}

TEST_F(FeatureDetectionTest, DrawCorners) {
    CornerResult r = detect_harris(gray);
    cv::Mat colorOut = draw_corners(gray, r.mask, 3, {0, 255, 0});
    EXPECT_EQ(colorOut.channels(), 3);
    EXPECT_EQ(colorOut.size(), gray.size());
}

TEST_F(FeatureDetectionTest, SusanThrowsOnEmpty) {
    EXPECT_THROW(detect_susan(empty), std::invalid_argument);
}

TEST_F(FeatureDetectionTest, HarrisThrowsOnEmpty) {
    EXPECT_THROW(detect_harris(empty), std::invalid_argument);
}

} // anonymous namespace
