package com.brooth.blaze;

import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Paint;
import android.view.View;

/** Locally drawn chord tones and complete guitar shapes; no remote diagram data. */
final class ChordDiagramView extends View {
    private final Paint paint = new Paint(Paint.ANTI_ALIAS_FLAG);
    private int chord = -1;
    private boolean guitar;
    ChordDiagramView(Context context) { super(context); setContentDescription("Chord diagram"); }
    void show(int value, boolean guitar) {
        if(this.chord==value&&this.guitar==guitar)return;
        this.chord = value; this.guitar = guitar;
        StringBuilder notes = new StringBuilder();
        if (value >= 0) for (int pitch = 0; pitch < 12; pitch++) if (StudioChord.contains(value,pitch)) notes.append(notes.length() == 0 ? "" : ", ").append(ChordEngine.NOTES[pitch]);
        setContentDescription(value < 0 ? "No chord diagram" : StudioChord.label(value,0) + (guitar ? " guitar fingering" : " piano chord tones: " + notes));
        invalidate();
    }
    @Override protected void onDraw(Canvas canvas) {
        super.onDraw(canvas);
        if (chord < 0) return;
        float unit = getResources().getDisplayMetrics().density;
        paint.setTextSize(11 * getResources().getDisplayMetrics().scaledDensity); paint.setTextAlign(Paint.Align.CENTER);
        if (guitar) drawGuitar(canvas, unit); else drawPiano(canvas, unit);
    }
    private void drawPiano(Canvas canvas, float unit) {
        int[] whites = {5, 7, 9, 11, 0, 2, 4, 5, 7, 9, 11, 0, 2, 4};
        int[] blacks = {6, 8, 10, 1, 3, 6, 8, 10, 1, 3}, gaps = {1, 2, 3, 5, 6, 8, 9, 10, 12, 13};
        float width = (getWidth() - 12 * unit) / 14, left = 6 * unit, top = 4 * unit, bottom = getHeight() - 24 * unit;
        boolean[] marked = new boolean[12];
        for (int i = 0; i < whites.length; i++) {
            paint.setStyle(Paint.Style.FILL); paint.setColor(0xfff3f3f3);
            canvas.drawRect(left + i * width, top, left + (i + 1) * width - unit, bottom, paint);
            if (contains(whites[i]) && !marked[whites[i]]) { paint.setColor(0xffff8c42); canvas.drawCircle(left + (i + .5f) * width, bottom - 8 * unit, Math.min(4 * unit, width * .3f), paint); marked[whites[i]] = true; }
        }
        for (int i = 0; i < blacks.length; i++) {
            float centre = left + gaps[i] * width;
            paint.setColor(0xff101820);
            canvas.drawRect(centre - .3f * width, top, centre + .3f * width, top + (bottom - top) * .6f, paint);
            if (contains(blacks[i]) && !marked[blacks[i]]) { paint.setColor(0xffff8c42); canvas.drawCircle(centre, top + (bottom - top) * .48f, Math.min(3.5f * unit, width * .24f), paint); marked[blacks[i]] = true; }
        }
        StringBuilder notes = new StringBuilder();
        for (int n = 0; n < 12; n++) { int pitch = Math.floorMod(StudioChord.root(chord) + n, 12); if (contains(pitch)) notes.append(notes.length() == 0 ? "" : "  ").append(ChordEngine.NOTES[pitch]); }
        paint.setColor(0xffeeeeee); canvas.drawText(notes.toString(), getWidth() / 2f, getHeight() - 6 * unit, paint);
    }
    private boolean contains(int pitch) {
        return StudioChord.contains(chord,pitch);
    }
    private void drawGuitar(Canvas canvas, float unit) {
        int root = StudioChord.root(chord); boolean minor = StudioChord.quality(chord)==0;
        int eShift = Math.floorMod(root - 4, 12), aShift = Math.floorMod(root - 9, 12);
        int shift = Math.min(eShift, aShift);
        int[] frets = eShift <= aShift ? new int[]{0, 2, 2, minor ? 0 : 1, 0, 0} : new int[]{-1, 0, 2, 2, minor ? 1 : 2, 0};
        for (int i = 0; i < frets.length; i++) if (frets[i] >= 0) frets[i] += shift;
        if (!minor && root == 0) frets = new int[]{-1, 3, 2, 0, 1, 0};
        if (!minor && root == 2) frets = new int[]{-1, -1, 0, 2, 3, 2};
        if (!minor && root == 7) frets = new int[]{3, 2, 0, 0, 0, 3};
        if (minor && root == 2) frets = new int[]{-1, -1, 0, 2, 3, 1};
        if(StudioChord.quality(chord)>1){frets=StudioChord.voicing(chord);if(frets==null){paint.setColor(0xffa8b1c5);canvas.drawText("Use piano chord tones",getWidth()/2f,getHeight()/2f,paint);return;}}
        int lowest = 99, highest = 0; for (int fret : frets) { if (fret > 0) lowest = Math.min(lowest, fret); highest = Math.max(highest, fret); }
        int firstFret = highest <= 4 ? 1 : lowest;
        float spacing = Math.min(28 * unit, (getWidth() - 80 * unit) / 5), left = (getWidth() - spacing * 5) / 2;
        float top = 30 * unit, step = (getHeight() - top - 24 * unit) / 4;
        paint.setColor(0xffeeeeee); paint.setStrokeWidth(unit);
        for (int i = 0; i < 5; i++) canvas.drawLine(left, top + i * step, left + 5 * spacing, top + i * step, paint);
        for (int i = 0; i < 6; i++) {
            float x = left + i * spacing; canvas.drawLine(x, top, x, top + 4 * step, paint);
            canvas.drawText(frets[i] < 0 ? "×" : frets[i] == 0 ? "○" : Integer.toString(frets[i]), x, top - 9 * unit, paint);
            if (frets[i] > 0) { paint.setColor(0xffff8c42); canvas.drawCircle(x, top + (frets[i] - firstFret + .5f) * step, 5 * unit, paint); paint.setColor(0xffeeeeee); }
        }
        canvas.drawText(Integer.toString(firstFret), left - 18 * unit, top + step / 2, paint);
        canvas.drawText("E  A  D  G  B  e", getWidth() / 2f, getHeight() - 4 * unit, paint);
    }
}
