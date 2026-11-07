// Home Assistant may normalize RGB intensity because brightness is separate.
// Compare both colors at full intensity, allowing one channel step for rounding.
export function colorsMatch(requested: number[], actual: number[] | null): boolean {
    if (
        actual === null ||
        [requested, actual].some((rgb) =>
            rgb.length !== 3 || rgb.some((value) =>
                !Number.isFinite(value) || value < 0 || value > 255
            )
        )
    ) return false;

    const requestedMax = Math.max(...requested);
    const actualMax = Math.max(...actual);
    // Black has no chromaticity; never equate it with a nonblack color.
    if (requestedMax === 0 || actualMax === 0) {
        return requestedMax === actualMax;
    }

    return requested.every((value, index) =>
        Math.abs(value * 255 / requestedMax - actual[index]! * 255 / actualMax) <= 1
    );
}
