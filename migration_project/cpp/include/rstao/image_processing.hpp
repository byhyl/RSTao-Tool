#pragma once

#include "rstao/common/types.hpp"

namespace rstao {

// ---- Individual operators ----

Image to_grayscale(const Image& src);

Image convert_color_space(const Image& src, const std::string& target);

Image linear_stretch(const Image& src, double low_percent = 2.0, double high_percent = 98.0);

Image histogram_equalize(const Image& src);

Image match_histogram(const Image& source, const Image& reference);

Image smooth(const Image& src, const std::string& method, int ksize);

Image sharpen(const Image& src, const std::string& method, double amount);

Image edge_detect(const Image& src, const std::string& mode);

Image morphology(const Image& src, const std::string& operation, int ksize, int iterations);

Image threshold_binary(const Image& src, const std::string& method, double value, int block_size = 11);

Image pca_component(const Image& src, int component_index);

Image ihs_intensity(const Image& src);

Image fft_filter(const Image& src, const std::string& mode, double radius);

Image normalized_difference(const Image& src, int band_a, int band_b);

// ---- Display helpers ----

Image display_preview(const Image& src, double low_percent = 2.0, double high_percent = 98.0);

// ---- Unified dispatch ----

ProcessingResult process(const Image& image, const std::string& op_id, const ParamMap& params = {});

} // namespace rstao
