from functools import lru_cache

from radiomics import featureextractor


@lru_cache(maxsize=1)
def get_radiomics_extractor() -> featureextractor.RadiomicsFeatureExtractor:
    extractor = featureextractor.RadiomicsFeatureExtractor(
        binWidth=25,
        resampledPixelSpacing=[1, 1, 1],
        normalize=True,
    )
    extractor.enableImageTypes(Original={}, LoG={"sigma": [1, 2, 3, 4, 5]}, Wavelet={})
    return extractor


def extract_selected_radiomics(image, mask_image, selected_features: list[str]) -> dict[str, float]:
    extractor = get_radiomics_extractor()
    result = extractor.execute(image, mask_image)

    selected_values: dict[str, float] = {}
    for csv_feature_name in selected_features:
        radiomics_key = csv_feature_name[:-2] if csv_feature_name.endswith("_C") else csv_feature_name
        if radiomics_key not in result:
            raise KeyError(f"Radiomics feature not found: {radiomics_key}")
        selected_values[csv_feature_name] = float(result[radiomics_key])

    return selected_values

