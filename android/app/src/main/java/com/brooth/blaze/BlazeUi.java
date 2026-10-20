package com.brooth.blaze;

import android.app.Activity;
import android.content.Context;
import android.content.res.ColorStateList;
import android.content.res.Configuration;
import android.graphics.Canvas;
import android.graphics.ColorFilter;
import android.graphics.Paint;
import android.graphics.Path;
import android.graphics.PixelFormat;
import android.graphics.RectF;
import android.graphics.Typeface;
import android.graphics.drawable.Drawable;
import android.graphics.drawable.GradientDrawable;
import android.graphics.drawable.LayerDrawable;
import android.graphics.drawable.RippleDrawable;
import android.graphics.drawable.StateListDrawable;
import android.os.Build;
import android.view.Gravity;
import android.view.View;
import android.view.WindowInsets;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.Spinner;
import android.widget.TextView;

/** Shared native surfaces and controls. Content remains responsible for its own layout. */
public final class BlazeUi {
    private final Context context;
    public final int background, surface, elevated, text, secondary, accent, accentText, border, softAccent;
    public final boolean dark;

    public BlazeUi(Context context) {
        this.context = context;
        dark = isDark(context);
        background = context.getColor(R.color.blaze_background);
        surface = context.getColor(R.color.blaze_surface);
        elevated = context.getColor(R.color.blaze_elevated);
        text = context.getColor(R.color.blaze_text);
        secondary = context.getColor(R.color.blaze_secondary);
        accent = context.getColor(R.color.blaze_accent);
        accentText = context.getColor(R.color.blaze_accent_text);
        border = context.getColor(R.color.blaze_border);
        softAccent = context.getColor(R.color.blaze_soft_accent);
    }

    private static boolean isDark(Context context) {
        return (context.getResources().getConfiguration().uiMode & Configuration.UI_MODE_NIGHT_MASK)
            == Configuration.UI_MODE_NIGHT_YES;
    }

    /** Call before super.onCreate so dialogs and framework widgets use the same theme. */
    public static void apply(Activity activity) {
        boolean dark = isDark(activity);
        activity.setTheme(dark ? R.style.BlazeThemeDark : R.style.BlazeTheme);
        int color = activity.getColor(R.color.blaze_background);
        activity.getWindow().setStatusBarColor(color);
        activity.getWindow().setNavigationBarColor(!dark && Build.VERSION.SDK_INT < 26 ? 0xff20201e : color);
        View decor = activity.getWindow().getDecorView();
        int flags = decor.getSystemUiVisibility() & ~View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR;
        if (!dark) flags |= View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR;
        if (Build.VERSION.SDK_INT >= 26) {
            flags &= ~View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR;
            if (!dark) flags |= View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR;
        }
        decor.setSystemUiVisibility(flags);
    }

    public int dp(float value) {
        return Math.round(value * context.getResources().getDisplayMetrics().density);
    }

    public GradientDrawable shape(int color, float radius) {
        GradientDrawable drawable = new GradientDrawable();
        drawable.setColor(color);
        drawable.setCornerRadius(dp(radius));
        return drawable;
    }

    public TextView label(String value, float size, int color) {
        TextView label = new TextView(context);
        label.setText(value);
        label.setTextSize(size);
        label.setTextColor(color);
        label.setFontFeatureSettings("kern");
        label.setIncludeFontPadding(false);
        label.setLineSpacing(dp(3), 1);
        return label;
    }

    public TextView heading(String value, float size) {
        TextView heading = label(value, size, text);
        heading.setTypeface(Typeface.create("sans-serif-medium", Typeface.NORMAL));
        heading.setLetterSpacing(size >= 24 ? -0.025f : -0.01f);
        if (Build.VERSION.SDK_INT >= 28) heading.setAccessibilityHeading(true);
        return heading;
    }

    public Button button(String value, boolean primary) {
        Button button = new Button(context);
        button.setText(value);
        styleButton(button, primary);
        return button;
    }

    public void styleButton(Button button, boolean primary) {
        button.setAllCaps(false);
        button.setTextSize(15);
        button.setTypeface(Typeface.create("sans-serif-medium", Typeface.NORMAL));
        button.setLetterSpacing(0);
        button.setGravity(Gravity.CENTER);
        button.setMinHeight(dp(50));
        button.setMinimumHeight(dp(50));
        button.setMinWidth(dp(48));
        button.setMinimumWidth(dp(48));
        button.setPadding(dp(16), dp(12), dp(16), dp(12));
        button.setElevation(0);
        button.setStateListAnimator(null);
        button.setBackgroundTintList(null);
        int foreground = primary ? accentText : text;
        button.setTextColor(new ColorStateList(new int[][]{
            new int[]{-android.R.attr.state_enabled}, new int[]{}
        }, new int[]{secondary, foreground}));
        button.setBackground(controlBackground(primary ? accent : elevated, 15));
    }

    private Drawable controlBackground(int fill, float radius) {
        StateListDrawable states = new StateListDrawable();
        GradientDrawable focused = shape(fill, radius);
        focused.setStroke(dp(2), accent);
        states.addState(new int[]{-android.R.attr.state_enabled}, shape(elevated, radius));
        states.addState(new int[]{android.R.attr.state_focused}, focused);
        states.addState(new int[]{}, shape(fill, radius));
        return new RippleDrawable(ColorStateList.valueOf(dark ? 0x26ffffff : 0x18000000), states,
            shape(0xffffffff, radius));
    }

    /** Stateful fill for segmented controls and navigation without losing press or focus feedback. */
    public Drawable interactiveSurface(int fill, float radius) {
        return controlBackground(fill, radius);
    }

    public LinearLayout column() {
        LinearLayout column = new LinearLayout(context);
        column.setOrientation(LinearLayout.VERTICAL);
        return column;
    }

    public LinearLayout card() {
        LinearLayout card = column();
        card.setPadding(dp(20), dp(20), dp(20), dp(20));
        card.setBackground(shape(surface, 22));
        return card;
    }

    public View divider() {
        View divider = new View(context);
        divider.setBackgroundColor(border);
        divider.setLayoutParams(new LinearLayout.LayoutParams(-1, Math.max(1, dp(1))));
        divider.setImportantForAccessibility(View.IMPORTANT_FOR_ACCESSIBILITY_NO);
        return divider;
    }

    public void gap(LinearLayout parent, float size) {
        View space = new View(context);
        space.setImportantForAccessibility(View.IMPORTANT_FOR_ACCESSIBILITY_NO);
        parent.addView(space, new LinearLayout.LayoutParams(1, dp(size)));
    }

    /** API 35 enforces edge-to-edge; earlier versions already inset ordinary activity content. */
    public void inset(View view) {
        if (Build.VERSION.SDK_INT < 35) return;
        final int left = view.getPaddingLeft(), top = view.getPaddingTop();
        final int right = view.getPaddingRight(), bottom = view.getPaddingBottom();
        view.setOnApplyWindowInsetsListener((target, insets) -> {
            android.graphics.Insets safe = insets.getInsets(WindowInsets.Type.systemBars() | WindowInsets.Type.displayCutout());
            target.setPadding(left + safe.left, top + safe.top, right + safe.right, bottom + safe.bottom);
            return insets;
        });
        view.requestApplyInsets();
    }

    public void styleInput(EditText input) {
        input.setTextSize(16);
        input.setTextColor(text);
        input.setHintTextColor(secondary);
        input.setMinHeight(dp(56));
        input.setPadding(dp(16), dp(16), dp(16), dp(16));
        input.setBackgroundTintList(null);
        input.setBackground(controlBackground(elevated, 15));
    }

    public void styleSpinner(Spinner spinner) {
        spinner.setMinimumHeight(dp(52));
        spinner.setPaddingRelative(dp(12), dp(6), dp(42), dp(6));
        spinner.setBackgroundTintList(null);
        LayerDrawable background = new LayerDrawable(new Drawable[]{controlBackground(elevated, 15), icon("chevron", secondary)});
        background.setLayerGravity(1, Gravity.END | Gravity.CENTER_VERTICAL);
        background.setLayerSize(1, dp(20), dp(20));
        background.setLayerInsetRelative(1, 0, 0, dp(14), 0);
        spinner.setBackground(background);
        spinner.setPopupBackgroundDrawable(shape(surface, 15));
    }

    /** Small original stroke icons; names are semantic rather than tied to a platform font. */
    public Drawable icon(String name, int color) {
        Drawable icon = new LineIcon(name, color, dp(24));
        icon.setBounds(0, 0, dp(24), dp(24));
        return icon;
    }

    private static final class LineIcon extends Drawable {
        private final Paint paint = new Paint(Paint.ANTI_ALIAS_FLAG);
        private final String name;
        private final int size;

        LineIcon(String name, int color, int size) {
            this.name = name;
            this.size = size;
            paint.setColor(color);
            paint.setStrokeWidth(1.8f);
            paint.setStrokeCap(Paint.Cap.ROUND);
            paint.setStrokeJoin(Paint.Join.ROUND);
        }

        @Override public void draw(Canvas canvas) {
            canvas.save();
            canvas.translate(getBounds().left, getBounds().top);
            canvas.scale(getBounds().width() / 24f, getBounds().height() / 24f);
            paint.setStyle(Paint.Style.STROKE);
            switch (name) {
                case "download":
                    line(canvas, 12, 3, 12, 15); path(canvas, 7,10,12,15,17,10);
                    path(canvas, 4,16,4,20,20,20,20,16); break;
                case "library":
                    canvas.drawRoundRect(4, 5, 20, 21, 2, 2, paint);
                    line(canvas, 7, 2, 17, 2); line(canvas, 8, 10, 16, 10); line(canvas, 8, 15, 14, 15); break;
                case "music":
                    path(canvas, 9,17,9,5,20,3,20,15); line(canvas, 9, 9, 20, 7);
                    canvas.drawOval(3, 15, 9, 20, paint); canvas.drawOval(14, 13, 20, 18, paint); break;
                case "back": path(canvas, 14,5,7,12,14,19); break;
                case "arrow": path(canvas, 9,5,16,12,9,19); break;
                case "chevron": path(canvas, 6,9,12,15,18,9); break;
                case "expand":
                    path(canvas, 3,9,3,3,9,3); path(canvas, 15,3,21,3,21,9);
                    path(canvas, 21,15,21,21,15,21); path(canvas, 9,21,3,21,3,15); break;
                case "play":
                    paint.setStyle(Paint.Style.FILL); Path triangle = new Path();
                    triangle.moveTo(8, 4); triangle.lineTo(20, 12); triangle.lineTo(8, 20); triangle.close();
                    canvas.drawPath(triangle, paint); break;
                case "pause":
                    paint.setStyle(Paint.Style.FILL); canvas.drawRoundRect(6, 4, 10, 20, 1, 1, paint);
                    canvas.drawRoundRect(14, 4, 18, 20, 1, 1, paint); break;
                case "more":
                    paint.setStyle(Paint.Style.FILL); for (int i = 5; i <= 19; i += 7) canvas.drawCircle(i, 12, 1.7f, paint); break;
                case "link":
                    canvas.save(); canvas.rotate(-45, 12, 12);
                    canvas.drawRoundRect(new RectF(8, 2, 16, 13), 4, 4, paint);
                    canvas.drawRoundRect(new RectF(8, 11, 16, 22), 4, 4, paint);
                    canvas.restore(); break;
                case "plus": line(canvas, 12, 5, 12, 19); line(canvas, 5, 12, 19, 12); break;
                case "folder":
                    Path folder = new Path(); folder.moveTo(3, 8); folder.lineTo(3, 5); folder.lineTo(10, 5);
                    folder.lineTo(12, 8); folder.lineTo(21, 8); folder.lineTo(21, 20); folder.lineTo(3, 20); folder.close();
                    canvas.drawPath(folder, paint); break;
                case "check": path(canvas, 5,12,10,17,20,6); break;
                case "clock":
                    canvas.drawCircle(12, 12, 9, paint); path(canvas, 12,7,12,12,16,14); break;
                case "settings":
                    canvas.drawCircle(12, 12, 7, paint); canvas.drawCircle(12, 12, 2.5f, paint);
                    for (int i = 0; i < 8; i++) { canvas.save(); canvas.rotate(i * 45, 12, 12); line(canvas, 12, 2, 12, 5); canvas.restore(); } break;
                default: canvas.drawCircle(12, 12, 8, paint); line(canvas, 12, 8, 12, 16);
            }
            canvas.restore();
        }

        private void line(Canvas canvas, float x1, float y1, float x2, float y2) { canvas.drawLine(x1, y1, x2, y2, paint); }
        private void path(Canvas canvas, float... points) {
            Path path = new Path(); path.moveTo(points[0], points[1]);
            for (int i = 2; i < points.length; i += 2) path.lineTo(points[i], points[i + 1]);
            canvas.drawPath(path, paint);
        }
        @Override public void setAlpha(int alpha) { paint.setAlpha(alpha); invalidateSelf(); }
        @Override public void setColorFilter(ColorFilter filter) { paint.setColorFilter(filter); invalidateSelf(); }
        @Override public int getOpacity() { return PixelFormat.TRANSLUCENT; }
        @Override public int getIntrinsicWidth() { return size; }
        @Override public int getIntrinsicHeight() { return size; }
    }
}
