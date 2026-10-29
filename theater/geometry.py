"""Stage coordinates shared by choreography, pointer hit tests and drawing."""

def stage_metrics(count, width, height, labels=False, ensemble=False):
    scale = min(1.5, height / 170)
    size = max(38, min(int(height * .72), int(width / (count + 1) * .85)))
    floor = height - (int(19 * scale) if labels else 2)
    if ensemble:
        size = max(18, min(int(height * .43), int(width / 9 * .88)))
    return size, floor


def stage_position(actor, index, count, width, size, floor, ensemble=False):
    if ensemble and 'departure' not in actor:
        row, column = (0, index) if index < 8 else (1, index - 8)
        row_count = 8 if row == 0 else 9
        return int((column + 1) * width / (row_count + 1)), floor - int(size * .58) if row == 0 else floor, int(size * .9) if row == 0 else size
    return int(actor['x'] * (width - size) + size / 2), floor, size


def stage_x(pixel_x, width, size):
    return max(.07, min(.93, (pixel_x - size / 2) / max(1, width - size)))
