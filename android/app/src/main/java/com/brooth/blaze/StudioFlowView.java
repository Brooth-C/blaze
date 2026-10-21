package com.brooth.blaze;

import android.content.Context;
import android.graphics.*;
import android.os.Bundle;
import android.view.*;
import androidx.core.view.ViewCompat;
import androidx.core.view.accessibility.AccessibilityNodeInfoCompat;
import androidx.customview.widget.ExploreByTouchHelper;
import java.util.*;

/** Continuous player-driven chord strip. Beat cells use measured timestamps. */
final class StudioFlowView extends View {
    interface Seek {
        void to(long time);
        default void preview(long time) { }
        default void cancelPreview() { }
    }
    Seek seek;
    private StudioTimeline timeline;
    private long position;
    private int transpose;
    private float downX, downY;
    private boolean moved, dragging;
    private double dragCoordinate;
    private long dragTarget;
    private final Paint paint = new Paint(Paint.ANTI_ALIAS_FLAG), text = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Path trackClip = new Path();
    private final Access access;
    private final BlazeUi ui;
    StudioFlowView(Context c) {
        super(c); ui = new BlazeUi(c); setFocusable(true); setImportantForAccessibility(IMPORTANT_FOR_ACCESSIBILITY_YES);
        setContentDescription("Chord timeline. Swipe or tap to seek.");
        access = new Access(this); ViewCompat.setAccessibilityDelegate(this, access);
    }
    void show(StudioTimeline map, int shift) { timeline = map; transpose = shift; invalidate(); access.invalidateRoot(); }
    void position(long time) {
        if (timeline == null || dragging) return;
        long next = Math.max(0, Math.min(timeline.duration, time)); if (next == position) return;
        boolean changed = timeline.state(next).chord != timeline.state(position).chord;
        position = next; invalidate(); if (changed) access.invalidateRoot();
    }
    private float dp(float value) { return value * getResources().getDisplayMetrics().density; }
    private float sp(float value) { return value * getResources().getDisplayMetrics().scaledDensity; }
    private float cellWidth() { return Math.max(dp(64), getWidth() / 5f); }
    private float playhead() { return getWidth() * .32f; }
    private boolean measured() { return timeline != null && timeline.beatTimes.length > 1; }
    private double coordinate(long time) {
        if (!measured()) return time / 1000.0;
        long[] beats = timeline.beatTimes; int index = StudioTimeline.upper(beats, time) - 1;
        if (index < 0) return (double)(time - beats[0]) / (beats[1] - beats[0]);
        if (index >= beats.length - 1) return beats.length - 1 + (double)(time - beats[beats.length - 1]) / (beats[beats.length - 1] - beats[beats.length - 2]);
        return index + (double)(time - beats[index]) / (beats[index + 1] - beats[index]);
    }
    private long timeAt(double value) {
        if (!measured()) return Math.round(value * 1000);
        long[] beats = timeline.beatTimes; int index = (int)Math.floor(value);
        if (index < 0) return Math.round(beats[0] + value * (beats[1] - beats[0]));
        if (index >= beats.length - 1) return Math.round(beats[beats.length - 1] + (value - beats.length + 1) * (beats[beats.length - 1] - beats[beats.length - 2]));
        return Math.round(beats[index] + (value - index) * (beats[index + 1] - beats[index]));
    }
    private float x(long time) { return playhead() + (float)(coordinate(time) - coordinate(position)) * cellWidth(); }
    private long time(float x) { return Math.max(0, Math.min(timeline.duration, timeAt(coordinate(position) + (x - playhead()) / cellWidth()))); }
    static String visibleChord(int chord, int shift) { return chord < 0 ? "" : StudioChord.label(chord, shift); }
    @Override protected void onDraw(Canvas canvas) {
        super.onDraw(canvas); float top = dp(22), bottom = getHeight() - dp(8);
        paint.setColor(ui.surface); canvas.drawRoundRect(0, top, getWidth(), bottom, dp(16), dp(16), paint);
        if (timeline == null) { text.setColor(ui.secondary); text.setTextSize(sp(13)); text.setTypeface(Typeface.DEFAULT); String prompt = "Your chord timeline"; while(text.measureText(prompt) > getWidth() - dp(32) && text.getTextSize() > sp(10)) text.setTextSize(text.getTextSize() - 1); canvas.drawText(prompt, dp(16), (top + bottom - text.ascent() - text.descent()) / 2, text); return; }
        trackClip.reset(); trackClip.addRoundRect(0, top, getWidth(), bottom, dp(16), dp(16), Path.Direction.CW);
        double centre = coordinate(position); int start = (int)Math.floor(centre - playhead() / cellWidth()) - 1, finish = (int)Math.ceil(centre + (getWidth() - playhead()) / cellWidth()) + 1;
        text.setTypeface(Typeface.DEFAULT); text.setTextSize(sp(11)); text.setColor(ui.secondary);
        for (int beat = start; beat <= finish; beat++) {
            long timestamp = timeAt(beat); if (timestamp < 0 || timestamp >= timeline.duration) continue;
            float left = playhead() + (float)(beat - centre) * cellWidth();
            paint.setColor(ui.border); paint.setStrokeWidth(dp(1)); canvas.drawLine(left, top, left, bottom, paint);
            if (!measured()) canvas.drawText((timestamp / 1000) + "s", left + dp(4), dp(16), text);
        }
        for (int i = 0; i < timeline.measures.size(); i++) {
            StudioTimeline.Measure measure = timeline.measures.get(i); if ("unknown".equals(measure.kind) || "lead-in".equals(measure.kind)) continue;
            float left = x(measure.start); if (left < 0 || left > getWidth()) continue;
            paint.setColor(ui.secondary); paint.setStrokeWidth(dp(2)); canvas.drawLine(left, top, left, bottom, paint);
            canvas.drawText("Bar " + measure.barNumber, left + dp(5), dp(16), text);
        }
        int previous = Integer.MIN_VALUE;
        for (int i = 0; i < timeline.chords.size(); i++) {
            ChordEngine.Event event = timeline.chords.get(i); String label = visibleChord(event.chord, transpose); boolean repeated = previous == event.chord; previous = event.chord;
            float left = x(event.startMs), right = x(event.endMs); if (label.isEmpty() || right < 0 || left > getWidth()) continue;
            if (position >= event.startMs && position < event.endMs) {
                canvas.save(); canvas.clipPath(trackClip);
                paint.setColor(ui.softAccent); canvas.drawRect(Math.max(0, left), top, Math.min(getWidth(), right), bottom, paint);
                canvas.restore();
            }
            if (repeated && left >= 0) continue;
            int next = i + 1; while (next < timeline.chords.size() && timeline.chords.get(next).chord == event.chord) next++;
            float nameX = Math.max(dp(8), left + dp(8)), available = getWidth() - dp(6) - nameX;
            if (next < timeline.chords.size()) available = Math.min(available, x(timeline.chords.get(next).startMs) - nameX - dp(4));
            if (available < dp(12)) continue;
            text.setTypeface(Typeface.create(Typeface.DEFAULT, Typeface.BOLD)); text.setTextSize(Math.min(sp(28), (bottom - top) * .64f));
            if (text.measureText(label) > available) text.setTextSize(Math.max(sp(12), text.getTextSize() * available / text.measureText(label)));
            text.setColor(position >= event.startMs && position < event.endMs ? ui.accent : ui.text);
            canvas.save(); canvas.clipRect(nameX, top, Math.max(nameX, nameX + available), bottom); canvas.drawText(label, nameX, (top + bottom - text.ascent() - text.descent()) / 2, text); canvas.restore();
        }
        paint.setColor(ui.accent); paint.setStrokeWidth(dp(2)); canvas.drawLine(playhead(), top - dp(5), playhead(), bottom + dp(4), paint); canvas.drawCircle(playhead(), top - dp(5), dp(3), paint);
    }
    @Override public boolean onTouchEvent(MotionEvent event) {
        if (timeline == null || seek == null) return false;
        if (event.getAction() == MotionEvent.ACTION_DOWN) {
            downX = event.getX(); downY = event.getY(); moved = false; dragging = true;
            dragCoordinate = coordinate(position); dragTarget = position; return true;
        }
        if (event.getAction() == MotionEvent.ACTION_MOVE) {
            if (!moved && Math.hypot(event.getX() - downX, event.getY() - downY) > ViewConfiguration.get(getContext()).getScaledTouchSlop()) {
                // Let a scrolling workspace own vertical gestures.
                if (Math.abs(event.getY() - downY) > Math.abs(event.getX() - downX)) { dragging = false; seek.cancelPreview(); return false; }
                moved = true; getParent().requestDisallowInterceptTouchEvent(true);
            }
            if (moved) {
                // Anchor the gesture to its initial timeline coordinate. Feeding each preview
                // back into time(x) moved the origin and made a small drag jump far ahead.
                dragTarget = Math.max(0, Math.min(timeline.duration, timeAt(dragCoordinate + (event.getX() - playhead()) / cellWidth())));
                position = dragTarget; invalidate(); seek.preview(dragTarget);
            }
            return true;
        }
        if (event.getAction() == MotionEvent.ACTION_UP) {
            if (!dragging) return false;
            long target = moved ? dragTarget : time(event.getX()); dragging = false;
            if (!moved) performClick(); getParent().requestDisallowInterceptTouchEvent(false);
            seek.to(target); access.invalidateRoot(); return true;
        }
        if (event.getAction() == MotionEvent.ACTION_CANCEL) {
            dragging = false; getParent().requestDisallowInterceptTouchEvent(false); seek.cancelPreview(); return true;
        }
        return false;
    }
    @Override public boolean performClick() { super.performClick(); return true; }
    @Override public boolean onKeyDown(int code, KeyEvent event) {
        if (timeline == null || seek == null) return super.onKeyDown(code, event); long target;
        if (code == KeyEvent.KEYCODE_DPAD_LEFT) target = timeAt(coordinate(position) - 1); else if (code == KeyEvent.KEYCODE_DPAD_RIGHT) target = timeAt(coordinate(position) + 1); else if (code == KeyEvent.KEYCODE_MOVE_HOME) target = 0; else if (code == KeyEvent.KEYCODE_MOVE_END) target = timeline.duration; else return super.onKeyDown(code, event);
        seek.to(Math.max(0, Math.min(timeline.duration, target))); return true;
    }
    @Override public boolean dispatchHoverEvent(MotionEvent event) { return access.dispatchHoverEvent(event) || super.dispatchHoverEvent(event); }
    private List<Integer> visibleEvents() {
        List<Integer> ids = new ArrayList<>(); if (timeline != null) for (int i = 0; i < timeline.chords.size(); i++) { ChordEngine.Event event = timeline.chords.get(i); if (event.chord >= 0 && x(event.endMs) > 0 && x(event.startMs) < getWidth()) ids.add(i); } return ids;
    }
    private final class Access extends ExploreByTouchHelper {
        Access(View view) { super(view); }
        @Override protected int getVirtualViewAt(float px, float py) { if (timeline == null) return INVALID_ID; long target = time(px); for (int id : visibleEvents()) { ChordEngine.Event event = timeline.chords.get(id); if (target >= event.startMs && target < event.endMs) return id; } return INVALID_ID; }
        @Override protected void getVisibleVirtualViews(List<Integer> ids) { ids.addAll(visibleEvents()); }
        @Override protected void onPopulateNodeForVirtualView(int id, AccessibilityNodeInfoCompat node) {
            if (timeline == null || id < 0 || id >= timeline.chords.size()) { node.setContentDescription("Chord timeline"); node.setBoundsInParent(new Rect(0, 0, 1, 1)); node.setEnabled(false); return; }
            ChordEngine.Event event = timeline.chords.get(id); node.setContentDescription(visibleChord(event.chord, transpose) + ", seek to " + String.format(Locale.ROOT, "%.1f seconds", event.startMs / 1000.0)); node.setClassName("android.widget.Button");
            int left = Math.max(0, Math.round(x(event.startMs))), right = Math.min(getWidth(), Math.round(x(event.endMs))); node.setBoundsInParent(new Rect(left, 0, Math.max(left + 1, right), getHeight())); node.addAction(AccessibilityNodeInfoCompat.ACTION_CLICK);
        }
        @Override protected boolean onPerformActionForVirtualView(int id, int action, Bundle args) { if (timeline == null || seek == null || id < 0 || id >= timeline.chords.size() || action != AccessibilityNodeInfoCompat.ACTION_CLICK) return false; seek.to(timeline.chords.get(id).startMs); return true; }
    }
}
