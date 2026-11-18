MIN_GRAY = 0
MAX_GRAY = 255


def validate_threshold(threshold: int) -> None:
    if type(threshold) is not int or not MIN_GRAY <= threshold <= MAX_GRAY:
        raise ValueError('gray threshold must be an integer between 0 and 255')


def threshold_total(threshold: int, pixel_count: int) -> int:
    validate_threshold(threshold)
    if type(pixel_count) is not int or pixel_count <= 0:
        raise ValueError('a grade requires a positive integer pixel count')
    return threshold * pixel_count
