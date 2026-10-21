package com.brooth.blaze;

import android.content.Context;
import android.graphics.Canvas;
import android.graphics.ColorFilter;
import android.graphics.Paint;
import android.graphics.Path;
import android.graphics.PixelFormat;
import android.graphics.RectF;
import android.graphics.drawable.Drawable;

/** Original small native icons drawn in the same 24-unit coordinate system. */
public final class DiscoveryIcons {
    private DiscoveryIcons() { }

    public static Drawable get(Context context, String name, int color) {
        return new Icon(name == null ? "more" : name, color,
            Math.round(24 * context.getResources().getDisplayMetrics().density));
    }

    private static final class Icon extends Drawable {
        private final String name;
        private final int size;
        private final Paint ink = new Paint(Paint.ANTI_ALIAS_FLAG);
        private final Path path = new Path();
        private final RectF oval = new RectF();

        Icon(String name, int color, int size) {
            this.name = name; this.size = size;
            ink.setColor(color); ink.setStrokeWidth(1.7f);
            ink.setStrokeCap(Paint.Cap.ROUND); ink.setStrokeJoin(Paint.Join.ROUND);
        }

        private void line(Canvas canvas, float x1, float y1, float x2, float y2) {
            canvas.drawLine(x1, y1, x2, y2, ink);
        }

        private void poly(Canvas canvas, float... points) {
            path.reset(); path.moveTo(points[0], points[1]);
            for (int i = 2; i < points.length; i += 2) path.lineTo(points[i], points[i + 1]);
            canvas.drawPath(path, ink);
        }

        private void heart(Canvas canvas, boolean filled) {
            ink.setStyle(filled ? Paint.Style.FILL : Paint.Style.STROKE);
            path.reset(); path.moveTo(12, 20);
            path.cubicTo(9.5f, 18, 3, 13.8f, 3, 8.5f);
            path.cubicTo(3, 3, 9.2f, 2.6f, 12, 7);
            path.cubicTo(14.8f, 2.6f, 21, 3, 21, 8.5f);
            path.cubicTo(21, 13.8f, 14.5f, 18, 12, 20);
            path.close(); canvas.drawPath(path, ink);
        }

        @Override public void draw(Canvas canvas) {
            int saved = canvas.save();
            canvas.translate(getBounds().left, getBounds().top);
            canvas.scale(getBounds().width() / 24f, getBounds().height() / 24f);
            ink.setStyle(Paint.Style.STROKE);
            switch (name) {
                case "play":
                    ink.setStyle(Paint.Style.FILL);
                    path.reset(); path.moveTo(7, 4); path.lineTo(20, 12);
                    path.lineTo(7, 20); path.close(); canvas.drawPath(path, ink); break;
                case "pause":
                    ink.setStyle(Paint.Style.FILL);
                    oval.set(6, 4, 10, 20); canvas.drawRoundRect(oval, 1, 1, ink);
                    oval.set(14, 4, 18, 20); canvas.drawRoundRect(oval, 1, 1, ink); break;
                case "next": case "previous":
                    if (name.equals("previous")) { canvas.translate(24, 0); canvas.scale(-1, 1); }
                    ink.setStyle(Paint.Style.FILL);
                    path.reset(); path.moveTo(5, 5); path.lineTo(17, 12);
                    path.lineTo(5, 19); path.close(); canvas.drawPath(path, ink);
                    oval.set(18, 4, 20.5f, 20); canvas.drawRoundRect(oval, .8f, .8f, ink); break;
                case "search":
                    canvas.drawCircle(10.5f, 10.5f, 6.1f, ink); line(canvas, 15, 15, 20, 20); break;
                case "close":
                    line(canvas, 6, 6, 18, 18); line(canvas, 18, 6, 6, 18); break;
                case "back": poly(canvas, 15, 4, 7, 12, 15, 20); break;
                case "chevron": poly(canvas, 9, 5, 16, 12, 9, 19); break;
                case "more":
                    ink.setStyle(Paint.Style.FILL);
                    canvas.drawCircle(5, 12, 1.6f, ink); canvas.drawCircle(12, 12, 1.6f, ink);
                    canvas.drawCircle(19, 12, 1.6f, ink); break;
                case "more_vertical":
                    ink.setStyle(Paint.Style.FILL);
                    canvas.drawCircle(12, 5, 1.35f, ink); canvas.drawCircle(12, 12, 1.35f, ink);
                    canvas.drawCircle(12, 19, 1.35f, ink); break;
                case "heart": heart(canvas, false); break;
                case "heart_filled": heart(canvas, true); break;
                case "shuffle":
                    poly(canvas, 3, 6, 6, 6, 17, 18, 21, 18);
                    poly(canvas, 18, 15, 21, 18, 18, 21);
                    poly(canvas, 3, 18, 6, 18, 9, 14.5f);
                    poly(canvas, 14.5f, 8, 17, 5, 21, 5);
                    poly(canvas, 18, 2, 21, 5, 18, 8); break;
                case "repeat":
                    path.reset(); path.moveTo(4, 9); path.cubicTo(4, 5, 6, 4, 9, 4);
                    path.lineTo(20, 4); canvas.drawPath(path, ink);
                    poly(canvas, 17, 1.5f, 20, 4, 17, 7);
                    path.reset(); path.moveTo(20, 15); path.cubicTo(20, 19, 18, 20, 15, 20);
                    path.lineTo(4, 20); canvas.drawPath(path, ink);
                    poly(canvas, 7, 17, 4, 20, 7, 22.5f); break;
                case "download":
                    poly(canvas, 4, 15, 4, 20, 20, 20, 20, 15);
                    line(canvas, 12, 3, 12, 15); poly(canvas, 7, 11, 12, 16, 17, 11); break;
                case "library":
                    oval.set(6, 3, 20, 19); canvas.drawRoundRect(oval, 2, 2, ink);
                    poly(canvas, 3, 7, 3, 22, 17, 22);
                    poly(canvas, 12, 15, 12, 8, 17, 7, 17, 13);
                    oval.set(9, 14, 12, 17); canvas.drawOval(oval, ink);
                    oval.set(14, 12, 17, 15); canvas.drawOval(oval, ink); break;
                case "studio":
                    line(canvas, 3, 10, 3, 14); line(canvas, 7, 6, 7, 18);
                    line(canvas, 11, 3, 11, 21); line(canvas, 15, 7, 15, 17);
                    line(canvas, 19, 9, 19, 15); line(canvas, 23, 11, 23, 13); break;
                case "explore":
                    ink.setStyle(Paint.Style.FILL); path.reset(); path.moveTo(12, 1);
                    path.cubicTo(13, 7, 7, 9, 9, 13);
                    path.cubicTo(5, 11, 6, 7, 6, 7);
                    path.cubicTo(-1, 17, 6, 23, 12, 23);
                    path.cubicTo(20, 23, 25, 15, 18, 8);
                    path.cubicTo(19, 14, 15, 15, 15, 15);
                    path.cubicTo(17, 8, 14, 5, 12, 1); path.close(); canvas.drawPath(path, ink); break;
                case "profile":
                    canvas.drawCircle(12, 8, 4, ink);
                    path.reset(); path.moveTo(4, 22); path.lineTo(4, 19);
                    path.cubicTo(4, 12, 20, 12, 20, 19); path.lineTo(20, 22);
                    canvas.drawPath(path, ink); break;
                case "queue":
                    line(canvas, 4, 5, 20, 5); line(canvas, 4, 10, 20, 10);
                    line(canvas, 4, 15, 14, 15); line(canvas, 4, 20, 12, 20);
                    ink.setStyle(Paint.Style.FILL); path.reset(); path.moveTo(17, 14);
                    path.lineTo(23, 18); path.lineTo(17, 22); path.close(); canvas.drawPath(path, ink); break;
                default:
                    canvas.drawCircle(12, 12, 8, ink); break;
            }
            canvas.restoreToCount(saved);
        }

        @Override public void setAlpha(int alpha) { ink.setAlpha(alpha); invalidateSelf(); }
        @Override public void setColorFilter(ColorFilter filter) { ink.setColorFilter(filter); invalidateSelf(); }
        @Override public int getOpacity() { return PixelFormat.TRANSLUCENT; }
        @Override public int getIntrinsicWidth() { return size; }
        @Override public int getIntrinsicHeight() { return size; }
    }
}
