#include <gtest/gtest.h>
#include <rstao/image_processing.hpp>

#include <opencv2/imgproc.hpp>

using namespace rstao;

namespace {

cv::Mat makeColorImage() {
    cv::Mat img(64, 64, CV_8UC3);
    for (int y = 0; y < 64; ++y)
        for (int x = 0; x < 64; ++x)
            img.at<cv::Vec3b>(y, x) = cv::Vec3b(
                static_cast<uchar>(x * 4),
                static_cast<uchar>(y * 4),
                static_cast<uchar>(128));
    return img;
}

class ImageProcessingTest : public ::testing::Test {
protected:
    void SetUp() override {
        // Synthetic 64x64 BGR image with known content
        color = cv::Mat(64, 64, CV_8UC3);
        for (int y = 0; y < 64; ++y)
            for (int x = 0; x < 64; ++x)
                color.at<cv::Vec3b>(y, x) = cv::Vec3b(
                    static_cast<uchar>(x * 4),
                    static_cast<uchar>(y * 4),
                    static_cast<uchar>(128));
    }

    cv::Mat color;
    cv::Mat empty;
};

TEST_F(ImageProcessingTest, GrayscaleReturnsSingleChannel) {
    cv::Mat result = to_grayscale(color);
    EXPECT_EQ(result.channels(), 1);
    EXPECT_EQ(result.rows, 64);
    EXPECT_EQ(result.cols, 64);
}

TEST_F(ImageProcessingTest, GrayscaleThrowsOnEmpty) {
    EXPECT_THROW(to_grayscale(empty), std::invalid_argument);
}

TEST_F(ImageProcessingTest, ColorSpaceHSV) {
    cv::Mat result = convert_color_space(color, "HSV");
    EXPECT_EQ(result.channels(), 3);
    EXPECT_EQ(result.size(), color.size());
}

TEST_F(ImageProcessingTest, ColorSpaceLab) {
    cv::Mat result = convert_color_space(color, "Lab");
    EXPECT_EQ(result.channels(), 3);
    EXPECT_EQ(result.size(), color.size());
}

TEST_F(ImageProcessingTest, LinearStretchProducesUint8) {
    cv::Mat result = linear_stretch(color, 2.0, 98.0);
    EXPECT_EQ(result.depth(), CV_8U);
    EXPECT_EQ(result.size(), color.size());
    // Should cover full range after stretch
    double minVal, maxVal;
    cv::minMaxLoc(result, &minVal, &maxVal);
    EXPECT_LE(minVal, 10);
    EXPECT_GE(maxVal, 240);
}

TEST_F(ImageProcessingTest, HistogramEqualize) {
    cv::Mat result = histogram_equalize(color);
    EXPECT_EQ(result.depth(), CV_8U);
    EXPECT_EQ(result.size(), color.size());
    // Equalized image should have at least some non-zero values
    EXPECT_GT(cv::countNonZero(result), 0);
}

TEST_F(ImageProcessingTest, MatchHistogramSameImage) {
    cv::Mat srcGray = to_grayscale(color);
    cv::Mat result = match_histogram(srcGray, srcGray);
    // Matching to itself should produce nearly identical output
    double diff = cv::norm(srcGray, result, cv::NORM_L1);
    EXPECT_LT(diff, 500.0);
}

TEST_F(ImageProcessingTest, SmoothGaussian) {
    cv::Mat result = smooth(color, "gaussian", 5);
    EXPECT_EQ(result.size(), color.size());
    EXPECT_EQ(result.channels(), 3);
}

TEST_F(ImageProcessingTest, SmoothMedian) {
    cv::Mat result = smooth(color, "median", 5);
    EXPECT_EQ(result.size(), color.size());
}

TEST_F(ImageProcessingTest, SharpenUnsharpMask) {
    cv::Mat result = sharpen(color, "unsharp_mask", 1.0);
    EXPECT_EQ(result.size(), color.size());
    EXPECT_EQ(result.channels(), 3);
}

TEST_F(ImageProcessingTest, EdgeDetectCanny) {
    cv::Mat result = edge_detect(color, "canny");
    EXPECT_EQ(result.size(), color.size());
    EXPECT_EQ(result.depth(), CV_8U);
}

TEST_F(ImageProcessingTest, EdgeDetectMagnitude) {
    cv::Mat result = edge_detect(color, "magnitude");
    EXPECT_EQ(result.depth(), CV_8U);
    EXPECT_GT(cv::countNonZero(result), 0);
}

TEST_F(ImageProcessingTest, MorphologyErode) {
    cv::Mat result = morphology(color, "erode", 3, 1);
    EXPECT_EQ(result.size(), color.size());
}

TEST_F(ImageProcessingTest, MorphologyDilate) {
    cv::Mat result = morphology(color, "dilate", 3, 1);
    EXPECT_EQ(result.size(), color.size());
}

TEST_F(ImageProcessingTest, ThresholdOtsu) {
    cv::Mat result = threshold_binary(color, "otsu", 0);
    EXPECT_EQ(result.depth(), CV_8U);
    EXPECT_EQ(result.size(), color.size());
    // Otsu should produce both black and white pixels
    double minVal, maxVal;
    cv::minMaxLoc(result, &minVal, &maxVal);
    EXPECT_EQ(minVal, 0);
    EXPECT_EQ(maxVal, 255);
}

TEST_F(ImageProcessingTest, PCAOnMultiband) {
    cv::Mat result = pca_component(color, 0);
    EXPECT_EQ(result.depth(), CV_8U);
    EXPECT_EQ(result.rows, color.rows);
    EXPECT_EQ(result.cols, color.cols);
}

TEST_F(ImageProcessingTest, IHSIntensity) {
    cv::Mat result = ihs_intensity(color);
    EXPECT_EQ(result.channels(), 1);
    EXPECT_EQ(result.size(), color.size());
}

TEST_F(ImageProcessingTest, NormalizedDifference) {
    cv::Mat result = normalized_difference(color, 0, 1);
    EXPECT_EQ(result.depth(), CV_8U);
    EXPECT_EQ(result.size(), color.size());
}

TEST_F(ImageProcessingTest, NormalizedDifferenceThrowsOnSingleChannel) {
    cv::Mat gray = to_grayscale(color);
    EXPECT_THROW(normalized_difference(gray, 0, 1), std::invalid_argument);
}

TEST_F(ImageProcessingTest, DisplayPreview) {
    cv::Mat result = display_preview(color, 2.0, 98.0);
    EXPECT_EQ(result.depth(), CV_8U);
    EXPECT_EQ(result.size(), color.size());
}

TEST_F(ImageProcessingTest, ProcessDispatchGrayscale) {
    ProcessingResult r = process(color, "grayscale");
    EXPECT_FALSE(r.image.empty());
    EXPECT_EQ(r.image.channels(), 1);
}

TEST_F(ImageProcessingTest, ProcessDispatchInvalidOp) {
    EXPECT_THROW(process(color, "nonexistent_op"), std::invalid_argument);
}

TEST_F(ImageProcessingTest, ProcessDispatchEmptyImage) {
    EXPECT_THROW(process(empty, "grayscale"), std::invalid_argument);
}

// ---- Progress callback tests ----

TEST(ProgressCallback, ReceivesMilestones) {
    cv::Mat src = makeColorImage();
    std::vector<int> milestones;
    auto cb = [&](int p) { milestones.push_back(p); };

    ProcessingResult result = process(src, "grayscale", {}, cb);
    EXPECT_FALSE(result.image.empty());
    ASSERT_GE(milestones.size(), 2u);
    EXPECT_EQ(milestones.front(), 0);   // starts at 0
    EXPECT_EQ(milestones.back(), 100);  // ends at 100
}

TEST(ProgressCallback, PassesForAllOperators) {
    cv::Mat src = makeColorImage();
    std::vector<std::string> opIds = {
        "grayscale", "color_space", "linear_stretch", "histogram_equalization",
        "smooth", "sharpen", "edge_detect", "morphology", "threshold",
        "pca", "ihs_intensity", "fft_filter", "normalized_difference"
    };
    for (const auto& opId : opIds) {
        int finalPct = 0;
        auto cb = [&](int p) { finalPct = p; };
        ProcessingResult result = process(src, opId, {}, cb);
        EXPECT_FALSE(result.image.empty()) << "Operator: " << opId;
        EXPECT_EQ(finalPct, 100) << "Operator: " << opId;
    }
}

TEST(ProgressCallback, ParametrizedOperatorReceivesProgress) {
    cv::Mat src = makeColorImage();
    int lastPct = -1;
    auto cb = [&](int p) { lastPct = p; };
    ParamMap params;
    params["method"] = std::string("gaussian");
    params["ksize"] = 5;
    ProcessingResult result = process(src, "smooth", params, cb);
    EXPECT_FALSE(result.image.empty());
    EXPECT_EQ(lastPct, 100);
}

TEST(ProgressCallback, ExistingOverloadStillWorks) {
    cv::Mat src = makeColorImage();
    // Call the old overload (no callback) — must not crash or throw
    ProcessingResult result = process(src, "grayscale");
    EXPECT_FALSE(result.image.empty());
}

// ---- Cancel tests ----

TEST(Cancel, ThrowsOperationCanceled) {
    cv::Mat src = makeColorImage();
    auto cb = [&](int) -> void {
        throw OperationCanceled();
    };
    EXPECT_THROW(process(src, "grayscale", {}, cb), OperationCanceled);
}

} // anonymous namespace
