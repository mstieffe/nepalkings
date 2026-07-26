# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Behaviour tests for the mobile keyboard viewport handling in index.html.

The game canvas is fixed and letterboxed over the whole screen, so an open
virtual keyboard simply covers the lower half of it — including the field the
user is typing into.  ``index.html`` lifts the canvas by the overlap instead.
This runs that real page code against a fake DOM shaped like a landscape
phone.
"""

import json
from pathlib import Path
import shutil
import subprocess

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
INDEX_HTML = REPO_ROOT / 'nepal_kings/web/index.html'

# Landscape phone: 780x390 CSS px, canvas letterboxed 16:9 to 694x390 for a
# 854x480 pygame surface.  An open keyboard leaves the top 175px visible.
HARNESS = r"""
const fs = require('fs');
const html = fs.readFileSync(process.argv[2], 'utf8');
const start = html.indexOf(
    '    // Canvas-aligned native text fields receive mobile taps directly.');
const end = html.indexOf('\n    window.nk_prepare_audio_gate = function(){');
if (start < 0 || end < 0) throw new Error('keyboard bridge block not found');

function makeElement(tag) {
    return {
        tagName: tag, style: {}, value: '', disabled: false, handlers: {},
        setAttribute() {},
        addEventListener(name, fn) {
            (this.handlers[name] = this.handlers[name] || []).push(fn);
        },
        dispatch(name) {
            (this.handlers[name] || []).forEach(function (fn) {
                fn({key: '', preventDefault() {}, stopPropagation() {}});
            });
        },
        focus() { this.dispatch('focus'); },
        blur() { this.dispatch('blur'); },
        setSelectionRange() {},
        remove() {},
        appendChild() {},
    };
}

const CANVAS_W = 854, CANVAS_H = 480, CSS_W = 694, CSS_H = 390;
const canvas = makeElement('canvas');
canvas.width = CANVAS_W;
canvas.height = CANVAS_H;
canvas.getBoundingClientRect = function () {
    const match = /translateY\((-?\d+)px\)/.exec(this.style.transform || '');
    const shift = match ? Number(match[1]) : 0;
    const left = (780 - CSS_W) / 2;
    return {left: left, top: shift, width: CSS_W, height: CSS_H,
            right: left + CSS_W, bottom: CSS_H + shift};
};

const layer = makeElement('div');
const inputs = [];
layer.appendChild = function (element) { inputs.push(element); };
const timers = [];
const viewportHandlers = {};
global.window = {
    innerHeight: 390,
    visualViewport: {
        height: 390,
        offsetTop: 0,
        addEventListener(name, fn) {
            (viewportHandlers[name] = viewportHandlers[name] || []).push(fn);
        },
    },
    addEventListener() {},
    setTimeout(fn) { timers.push(fn); },
    nk_audio_resume() {},
};
global.document = {
    activeElement: null,
    getElementById(id) {
        if (id === 'nk-keyboard-layer') return layer;
        if (id === 'canvas') return canvas;
        return null;
    },
    createElement: makeElement,
    addEventListener() {},
};

eval(html.slice(start, end));

const scaleY = CSS_H / CANVAS_H;
function shift() {
    const match = /translateY\((-?\d+)px\)/.exec(canvas.style.transform || '');
    return match ? Number(match[1]) : 0;
}
function runTimers() { timers.splice(0).forEach(function (fn) { fn(); }); }
function resizeViewport(height) {
    window.visualViewport.height = height;
    (viewportHandlers.resize || []).forEach(function (fn) { fn(); });
}
function openKeyboard() { resizeViewport(175); }
function closeKeyboard() { resizeViewport(390); }
function fieldBox(y, h) {
    return {top: y * scaleY + shift(), bottom: (y + h) * scaleY + shift()};
}

const result = {};

// A low field (centred login form) with the keyboard open.
const LOW_Y = 300, LOW_H = 48;
window.nk_keyboard_register(
    'password', '', true, 64, 120, LOW_Y, 400, LOW_H, 'text');
const password = inputs[0];
result.resting = fieldBox(LOW_Y, LOW_H);
result.restingShift = shift();

openKeyboard();
password.dispatch('focus');
result.lifted = fieldBox(LOW_Y, LOW_H);
result.liftedShift = shift();
result.liftedInputTop = parseFloat(password.style.top);

// Repeated viewport/focus events must converge on one offset.
runTimers();
password.dispatch('focus');
runTimers();
result.settledShift = shift();

// Blur alone must not drop the canvas: the keyboard is still retracting and a
// tap already in flight would land somewhere else.
password.dispatch('blur');
runTimers();
result.shiftAfterBlur = shift();
closeKeyboard();
runTimers();
result.shiftAfterKeyboardClosed = shift();

// A field that is already clear of the keyboard must not move.
window.nk_keyboard_clear();
inputs.length = 0;
window.nk_keyboard_register(
    'username', '', false, 64, 120, 40, 400, LOW_H, 'text');
openKeyboard();
inputs[0].dispatch('focus');
result.highFieldShift = shift();

// Screen transitions reset the canvas.
inputs[0].dispatch('blur');
closeKeyboard();
window.nk_keyboard_register(
    'password', '', true, 64, 120, LOW_Y, 400, LOW_H, 'text');
openKeyboard();
inputs[inputs.length - 1].dispatch('focus');
result.beforeDisable = shift();
window.nk_keyboard_set_enabled(false);
result.afterDisable = shift();
window.nk_keyboard_set_enabled(true);
openKeyboard();
inputs[inputs.length - 1].dispatch('focus');
window.nk_keyboard_clear();
result.afterClear = shift();

result.visibleBottom = window.visualViewport.height;
console.log(JSON.stringify(result));
"""


@pytest.fixture(scope='module')
def keyboard_shift(tmp_path_factory):
    node = shutil.which('node')
    if not node:
        pytest.skip('node is required to exercise the page keyboard bridge')
    harness = tmp_path_factory.mktemp('web') / 'keyboard_shift.js'
    harness.write_text(HARNESS)
    output = subprocess.run(
        [node, str(harness), str(INDEX_HTML)],
        check=True, capture_output=True, text=True).stdout
    return json.loads(output)


def test_canvas_rests_unshifted_until_a_keyboard_opens(keyboard_shift):
    assert keyboard_shift['restingShift'] == 0
    # The field sits below the strip a keyboard would leave visible, which is
    # the whole reason the lift is needed.
    assert keyboard_shift['resting']['bottom'] > 175


def test_focused_field_is_lifted_fully_into_the_visible_strip(keyboard_shift):
    lifted = keyboard_shift['lifted']
    assert keyboard_shift['liftedShift'] < 0
    assert lifted['bottom'] <= keyboard_shift['visibleBottom']
    # ...and not so far that it leaves the top of the screen.
    assert lifted['top'] >= 0
    # The native input tracks the canvas, or taps would miss the field.
    assert keyboard_shift['liftedInputTop'] == pytest.approx(lifted['top'])


def test_repeated_viewport_events_do_not_drift_the_canvas(keyboard_shift):
    assert keyboard_shift['settledShift'] == keyboard_shift['liftedShift']


def test_canvas_drops_back_only_once_the_keyboard_has_retracted(keyboard_shift):
    assert keyboard_shift['shiftAfterBlur'] == keyboard_shift['liftedShift']
    assert keyboard_shift['shiftAfterKeyboardClosed'] == 0


def test_field_already_clear_of_the_keyboard_is_left_alone(keyboard_shift):
    assert keyboard_shift['highFieldShift'] == 0


def test_disabling_or_clearing_inputs_restores_the_canvas(keyboard_shift):
    assert keyboard_shift['beforeDisable'] < 0
    assert keyboard_shift['afterDisable'] == 0
    assert keyboard_shift['afterClear'] == 0
