#include "rstao/image_io.hpp"
#include "rstao/image_processing.hpp" // for percentileStretch

#include <opencv2/imgcodecs.hpp>
#include <opencv2/imgproc.hpp>

#include <fstream>
#include <stdexcept>

namespace rstao {

// ============================================================================
// Reading
// ============================================================================

Image read_image(const std::string& path) {
    cv::Mat img = cv::imread(path, cv::IMREAD_COLOR);
    if (img.empty())
        throw std::runtime_error("Failed to read image: " + path);
    // OpenCV reads as BGR — convert to RGB
    cv::Mat rgb;
    cv::cvtColor(img, rgb, cv::COLOR_BGR2RGB);
    return rgb;
}

Image read_raster_data(const std::string& path, const std::vector<int>& band_indices) {
    // Try multi-page TIFF first
    std::vector<cv::Mat> pages;
    if (cv::imreadmulti(path, pages, cv::IMREAD_ANYCOLOR | cv::IMREAD_ANYDEPTH)) {
        if (pages.empty())
            throw std::runtime_error("No pages found in: " + path);

        if (band_indices.empty()) {
            // Merge all pages into multi-channel
            cv::Mat merged;
            cv::merge(pages, merged);
            return merged;
        }

        // Select specific bands
        std::vector<cv::Mat> selected;
        for (int idx : band_indices) {
            if (idx >= 0 && idx < static_cast<int>(pages.size())) {
                selected.push_back(pages[idx]);
            }
        }
        if (selected.empty())
            throw std::runtime_error("No valid band indices for: " + path);
        if (selected.size() == 1)
            return selected[0];
        cv::Mat merged;
        cv::merge(selected, merged);
        return merged;
    }

    // Fallback: single image
    cv::Mat img = cv::imread(path, cv::IMREAD_UNCHANGED);
    if (img.empty())
        throw std::runtime_error("Failed to read raster: " + path);
    return img;
}

RasterMetadata read_metadata(const std::string& path) {
    RasterMetadata meta;

    // Quick size check
    cv::Mat img = cv::imread(path, cv::IMREAD_UNCHANGED);
    if (img.empty()) {
        // Try multi-page
        std::vector<cv::Mat> pages;
        if (cv::imreadmulti(path, pages, cv::IMREAD_ANYCOLOR | cv::IMREAD_ANYDEPTH) && !pages.empty()) {
            img = pages[0];
            meta.bands = static_cast<int>(pages.size());
        }
    }

    if (!img.empty()) {
        meta.width  = img.cols;
        meta.height = img.rows;
        meta.dtype  = img.type();
        if (meta.bands == 0)
            meta.bands = img.channels();
    }

    // CRS and geotransform left empty — GDAL is required for those
    return meta;
}

// ============================================================================
// Writing
// ============================================================================

bool save_image(const std::string& path, const Image& image) {
    if (image.empty()) return false;

    cv::Mat out;
    // Convert RGB to BGR for OpenCV writing
    if (image.channels() == 3) {
        cv::cvtColor(image, out, cv::COLOR_RGB2BGR);
    } else if (image.channels() == 4) {
        cv::cvtColor(image, out, cv::COLOR_RGBA2BGRA);
    } else {
        out = image;
    }

    return cv::imwrite(path, out);
}

bool save_geotiff(const std::string& source_path, const Image& image,
                  const std::string& output_path) {
    // Without GDAL, we can only do a plain TIFF save (no georeferencing)
    // OpenCV's imwrite does not preserve geotags.
    // For now, delegate to save_image.
    // TODO: use GDAL when available to copy georeferencing from source_path.
    return save_image(output_path, image);
}

// ============================================================================
// Preview
// ============================================================================

Image make_preview(const Image& src, double low_percent, double high_percent) {
    return display_preview(src, low_percent, high_percent);
}

} // namespace rstao
