package com.brooth.blaze;

import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Paint;
import android.view.View;

/** Original, locally drawn triad diagrams; no remote image or chord database. */
final class ChordDiagramView extends View {
    private final Paint paint = new Paint(Paint.ANTI_ALIAS_FLAG);
    private int chord = -1;
    private boolean guitar;
    ChordDiagramView(Context context) { super(context); setContentDescription("Chord diagram"); }
    void show(int value, boolean guitar) {
        if(this.chord==value&&this.guitar==guitar)return;
        this.chord = value; this.guitar = guitar;
        setContentDescription(value < 0 ? "No reliable chord diagram" : StudioChord.label(value,0) + (guitar ? " guitar fingering" : " piano notes"));
        invalidate();
    }
    @Override protected void onDraw(Canvas canvas) {
        super.onDraw(canvas);
        if (chord < 0) return;
        float unit = getResources().getDisplayMetrics().density;
        paint.setTextSize(12 * unit); paint.setTextAlign(Paint.Align.CENTER);
        if (guitar) drawGuitar(canvas, unit); else drawPiano(canvas, unit);
    }
    private void drawPiano(Canvas canvas, float unit) {
        int[] whites = {0, 2, 4, 5, 7, 9, 11}, blacks = {1, 3, 6, 8, 10}, gaps = {1, 2, 4, 5, 6};
        float width = (getWidth() - 24 * unit) / 7, left = 12 * unit, top = 8 * unit, bottom = getHeight() - 20 * unit;
        for (int i = 0; i < 7; i++) {
            paint.setStyle(Paint.Style.FILL); paint.setColor(contains(whites[i]) ? 0xffff8c42 : 0xffeeeeee);
            canvas.drawRect(left + i * width, top, left + (i + 1) * width - unit, bottom, paint);
            paint.setColor(0xff10131c); canvas.drawText(ChordEngine.NOTES[whites[i]], left + (i + .5f) * width, bottom - 6 * unit, paint);
        }
        for (int i = 0; i < 5; i++) {
            float centre = left + gaps[i] * width;
            paint.setColor(contains(blacks[i]) ? 0xffff8c42 : 0xff10131c);
            canvas.drawRect(centre - .3f * width, top, centre + .3f * width, top + (bottom - top) * .6f, paint);
        }
        paint.setColor(0xffeeeeee); canvas.drawText("Highlighted notes (choose a comfortable octave)", getWidth() / 2f, getHeight() - 3 * unit, paint);
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
        if(StudioChord.quality(chord)>1){frets=StudioChord.voicing(chord);if(frets==null){paint.setColor(0xffa8b1c5);canvas.drawText("No compact guitar shape · use piano notes",getWidth()/2f,getHeight()/2f,paint);return;}}
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
        canvas.drawText("E  A  D  G  B  e · standard tuning · fret numbers above", getWidth() / 2f, getHeight() - 4 * unit, paint);
    }
}
