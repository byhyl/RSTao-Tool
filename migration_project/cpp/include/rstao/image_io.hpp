#pragma once

#include "rstao/common/types.hpp"

#include <string>
#include <vector>

namespace rstao {

// ---- Reading ----

/// Read image from file (supports PNG, JPEG, BMP, TIFF via OpenCV).
/// Returns BGR (3-channel) or grayscale depending on file content.
Image read_image(const std::string& path);

/// Read specific bands from a multi-band raster.
/// If band_indices is empty, read all bands.
/// Uses OpenCV imreadmulti for TIFF; falls back to single imread for others.
Image read_raster_data(const std::string& path, const std::vector<int>& band_indices = {});

/// Read metadata without loading full pixel data.
/// CRS and geotransform are empty/null when GDAL is unavailable.
RasterMetadata read_metadata(const std::string& path);

// ---- Writing ----

/// Save image to file. Format is determined by extension.
/// Supports PNG, JPEG, BMP, TIFF.
bool save_image(const std::string& path, const Image& image);

/// Save result image with georeferencing copied from source (if source is GeoTIFF).
/// Falls back to plain save when GDAL is unavailable.
bool save_geotiff(const std::string& source_path, const Image& image,
                  const std::string& output_path);

// ---- Preview ----

/// Generate percentile-stretched 8-bit preview of any image.
Image make_preview(const Image& src, double low_percent = 2.0, double high_percent = 98.0);

} // namespace rstao
