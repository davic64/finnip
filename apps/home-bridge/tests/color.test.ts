import assert from "node:assert/strict";
import { test } from "vitest";
import { colorsMatch } from "../src/utils/color.js";

test("accepts sky blue normalized by the device", () => {
    assert.equal(colorsMatch([135, 206, 235], [146, 224, 255]), true);
});

test("accepts identical colors and proportional white", () => {
    assert.equal(colorsMatch([0, 255, 0], [0, 255, 0]), true);
    assert.equal(colorsMatch([128, 128, 128], [255, 255, 255]), true);
});

test("rejects different hue or saturation", () => {
    assert.equal(colorsMatch([135, 206, 235], [255, 224, 146]), false);
    assert.equal(colorsMatch([135, 206, 235], [255, 255, 255]), false);
    assert.equal(colorsMatch([0, 255, 0], [0, 255, 3]), false);
});

test("handles black, absent colors and invalid device values", () => {
    assert.equal(colorsMatch([0, 0, 0], [0, 0, 0]), true);
    assert.equal(colorsMatch([0, 0, 0], [255, 255, 255]), false);
    assert.equal(colorsMatch([255, 255, 255], [0, 0, 0]), false);
    for (const value of [null, [], [1, 2], [1, 2, 300], [NaN, 0, 0]]) {
        assert.equal(colorsMatch([135, 206, 235], value), false);
    }
});
