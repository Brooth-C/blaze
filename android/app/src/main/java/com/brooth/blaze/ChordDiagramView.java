package com.brooth.blaze;

import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Paint;
import android.view.View;

/** Locally drawn chord tones and complete guitar shapes; no remote diagram data. */
final class ChordDiagramView extends View {
    private final Paint paint = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final BlazeUi ui;
    private int chord = -1;
    private boolean guitar;
    ChordDiagramView(Context context) { super(context); ui = new BlazeUi(context); setContentDescription("Chord diagram"); }
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
        if (chord < 0) {
            paint.setStyle(Paint.Style.STROKE); paint.setStrokeWidth(ui.dp(1)); paint.setColor(ui.border);
            float centre = getHeight() / 2f, left = getWidth() * .25f, right = getWidth() * .75f;
            for (int line = -1; line <= 1; line++) canvas.drawLine(left, centre + ui.dp(10 * line), right, centre + ui.dp(10 * line), paint);
            paint.setStyle(Paint.Style.FILL); return;
        }
        float unit = getResources().getDisplayMetrics().density;
        paint.setTextSize(11 * getResources().getDisplayMetrics().scaledDensity); paint.setTextAlign(Paint.Align.CENTER);
        if (guitar) drawGuitar(canvas, unit); else drawPiano(canvas, unit);
    }
    private void drawPiano(Canvas canvas, float unit) {
        int[] whites = {0, 2, 4, 5, 7, 9, 11};
        int[] blacks = {1, 3, 6, 8, 10}, gaps = {1, 2, 4, 5, 6};
        float width = (getWidth() - 8 * unit) / 7f, left = 4 * unit, top = 8 * unit;
        float bottom = top + Math.max(12 * unit, Math.min(getHeight() - 30 * unit, width * 4.2f));
        float dot = Math.min(4 * unit, width * .19f);
        for (int i = 0; i < whites.length; i++) {
            paint.setStyle(Paint.Style.FILL); paint.setColor(0xfffcfcfd);
            canvas.drawRoundRect(left + i * width, top, left + (i + 1) * width - unit, bottom, 2 * unit, 2 * unit, paint);
            paint.setStyle(Paint.Style.STROKE); paint.setStrokeWidth(unit * .7f); paint.setColor(0xffbcbcc2);
            canvas.drawRoundRect(left + i * width, top, left + (i + 1) * width - unit, bottom, 2 * unit, 2 * unit, paint);
            paint.setStyle(Paint.Style.FILL);
            if (contains(whites[i])) { paint.setColor(ui.accent); canvas.drawCircle(left + (i + .5f) * width, bottom - 8 * unit, dot, paint); }
        }
        for (int i = 0; i < blacks.length; i++) {
            float centre = left + gaps[i] * width;
            paint.setColor(0xff242426);
            canvas.drawRoundRect(centre - .3f * width, top, centre + .3f * width, top + (bottom - top) * .61f, 2 * unit, 2 * unit, paint);
            if (contains(blacks[i])) { paint.setColor(0xffffb28b); canvas.drawCircle(centre, top + (bottom - top) * .43f, dot * .8f, paint); }
        }
        StringBuilder notes = new StringBuilder();
        for (int n = 0; n < 12; n++) { int pitch = Math.floorMod(StudioChord.root(chord) + n, 12); if (contains(pitch)) notes.append(notes.length() == 0 ? "" : " · ").append(ChordEngine.NOTES[pitch]); }
        paint.setColor(ui.secondary);
        paint.setTextSize(11 * getResources().getDisplayMetrics().scaledDensity);
        while (paint.measureText(notes.toString()) > getWidth() - 4 * unit && paint.getTextSize() > 8 * unit) paint.setTextSize(paint.getTextSize() - unit);
        canvas.drawText(notes.toString(), getWidth() / 2f, Math.min(getHeight() - 2 * unit, bottom + 17 * unit), paint);
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
        if(StudioChord.quality(chord)>1||StudioChord.bass(chord)!=root){frets=StudioChord.voicing(chord);if(frets==null){paint.setColor(ui.secondary);canvas.drawText("Use piano chord tones",getWidth()/2f,getHeight()/2f,paint);return;}}
        int lowest = 99, highest = 0; for (int fret : frets) { if (fret > 0) lowest = Math.min(lowest, fret); highest = Math.max(highest, fret); }
        int firstFret = highest <= 4 ? 1 : lowest;
        float spacing = Math.max(9 * unit, Math.min(24 * unit, (getWidth() - 40 * unit) / 5)), left = (getWidth() - spacing * 5) / 2;
        float top = Math.min(28 * unit, getHeight() * .24f), step = Math.max(4 * unit, (getHeight() - top - 24 * unit) / 4);
        paint.setColor(ui.secondary); paint.setStrokeWidth(unit);
        for (int i = 0; i < 5; i++) canvas.drawLine(left, top + i * step, left + 5 * spacing, top + i * step, paint);
        for (int i = 0; i < 6; i++) {
            float x = left + i * spacing; canvas.drawLine(x, top, x, top + 4 * step, paint);
            canvas.drawText(frets[i] < 0 ? "\u00d7" : frets[i] == 0 ? "\u25cb" : Integer.toString(frets[i]), x, top - 9 * unit, paint);
            if (frets[i] > 0) { paint.setColor(ui.accent); canvas.drawCircle(x, top + (frets[i] - firstFret + .5f) * step, 5 * unit, paint); paint.setColor(ui.secondary); }
        }
        canvas.drawText(Integer.toString(firstFret), left - 18 * unit, top + step / 2, paint);
        canvas.drawText("E  A  D  G  B  e", getWidth() / 2f, getHeight() - 4 * unit, paint);
    }
}
