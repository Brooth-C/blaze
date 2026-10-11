package com.brooth.blaze;

import android.Manifest;
import android.app.*;
import android.content.*;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.net.Uri;
import android.os.*;
import android.view.*;
import android.widget.*;
import androidx.core.content.FileProvider;
import java.io.*;
import java.util.*;

public class MainActivity extends Activity {
    private EditText url;
    private RadioGroup modes;
    private Button start, stop;
    private TextView state;
    private ProgressBar bar;
    private LinearLayout files;
    private final Handler handler = new Handler(Looper.getMainLooper());
    private boolean lastBusy = true;
    private File exportFile;
    private final int orange = Color.rgb(255, 140, 66);
    private final Runnable refresh = new Runnable() {
        @Override public void run() {
            state.setText(DownloadService.status);
            boolean busy = DownloadService.busy;
            start.setEnabled(!busy); stop.setEnabled(busy);
            bar.setIndeterminate(busy && DownloadService.progress < 0);
            if (DownloadService.progress >= 0) bar.setProgress((int) DownloadService.progress);
            if (lastBusy != busy) { lastBusy = busy; showFiles(); }
            handler.postDelayed(this, 500);
        }
    };

    @Override public void onCreate(Bundle saved) {
        super.onCreate(saved);
        ScrollView scroll = new ScrollView(this);
        scroll.setBackgroundColor(Color.rgb(16, 19, 28));
        LinearLayout root = new LinearLayout(this); root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(dp(24), dp(28), dp(24), dp(32)); scroll.addView(root);
        setContentView(scroll);
        if (Build.VERSION.SDK_INT >= 35) scroll.setOnApplyWindowInsetsListener((view, insets) -> {
            android.graphics.Insets safe = insets.getInsets(WindowInsets.Type.systemBars());
            view.setPadding(safe.left, safe.top, safe.right, safe.bottom); return insets;
        });
        LinearLayout brand = new LinearLayout(this); brand.setGravity(Gravity.CENTER_VERTICAL);
        ImageView logo = new ImageView(this); logo.setImageResource(R.drawable.blaze_logo);
        logo.setContentDescription("Blaze logo"); brand.addView(logo, new LinearLayout.LayoutParams(dp(64), dp(64)));
        TextView title = text("Blaze", 36); title.setTypeface(null, Typeface.BOLD); brand.addView(title); root.addView(brand);
        root.addView(text("A link. A tap. Yours to keep.", 17));
        gap(root, 28);
        root.addView(text("PASTE A LINK", 12));
        url = new EditText(this); url.setId(R.id.url_input); url.setSingleLine(true);
        url.setHint("https://…"); url.setTextColor(Color.WHITE); url.setHintTextColor(Color.GRAY);
        url.setInputType(android.text.InputType.TYPE_CLASS_TEXT | android.text.InputType.TYPE_TEXT_VARIATION_URI);
        url.setPadding(dp(16), dp(12), dp(16), dp(12)); url.setBackground(card()); root.addView(url);
        gap(root, 16);
        modes = new RadioGroup(this); modes.setOrientation(RadioGroup.HORIZONTAL); modes.setId(R.id.download_mode);
        for (int i=0;i<2;i++) { RadioButton b = new RadioButton(this); b.setId(i==0 ? R.id.video_mode : R.id.audio_mode); b.setText(i==0 ? "Video" : "Audio"); b.setTextColor(Color.WHITE); modes.addView(b); }
        modes.check(R.id.video_mode); root.addView(modes);
        root.addView(text("Audio keeps its original format. Video includes sound.\nOne item at a time; no playlists or MP3 conversion yet.", 13));
        gap(root, 18);
        start = button("Download", root); start.setOnClickListener(v -> download());
        stop = button("Stop download", root); stop.setOnClickListener(v -> startService(new Intent(this, DownloadService.class).setAction("STOP")));
        gap(root, 16);
        state = text("Ready for your next download", 15); root.addView(state);
        bar = new ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal); bar.setMax(100); root.addView(bar);
        gap(root, 28);
        TextView heading = text("Saved files", 22); heading.setTypeface(null, Typeface.BOLD); root.addView(heading);
        root.addView(text("Save a copy to Downloads or share it. App files are removed if you uninstall Blaze.", 13));
        files = new LinearLayout(this); files.setOrientation(LinearLayout.VERTICAL); root.addView(files);
        gap(root, 24);
        Button about = button("About Blaze", root); about.setOnClickListener(v -> about());
        root.addView(text("Android preview · © 2026 Brooth-C", 12));
        if (saved != null) { url.setText(saved.getString("url", "")); modes.check(saved.getInt("mode",R.id.video_mode)); String path=saved.getString("export"); if(path!=null)exportFile=new File(path); }
        else receive(getIntent());
    }

    private void download() {
        String value=url.getText().toString().trim(); Uri link=Uri.parse(value);
        if (!"https".equalsIgnoreCase(link.getScheme()) || link.getHost()==null || link.getUserInfo()!=null) { url.setError("Paste a complete HTTPS link"); return; }
        if (Build.VERSION.SDK_INT>=33 && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS)!=android.content.pm.PackageManager.PERMISSION_GRANTED)
            requestPermissions(new String[]{Manifest.permission.POST_NOTIFICATIONS}, 2);
        Intent request=new Intent(this,DownloadService.class).putExtra("url",value).putExtra("mode",modes.getCheckedRadioButtonId()==R.id.audio_mode ? "audio" : "video");
        if(Build.VERSION.SDK_INT>=26)startForegroundService(request); else startService(request);
        start.setEnabled(false);
    }
    private void receive(Intent intent) {
        if(Intent.ACTION_SEND.equals(intent.getAction())) {
            String value=intent.getStringExtra(Intent.EXTRA_TEXT);
            if(value!=null) { java.util.regex.Matcher m=java.util.regex.Pattern.compile("https://\\S+").matcher(value); if(m.find())url.setText(m.group()); }
        }
    }
    @Override protected void onNewIntent(Intent intent) { super.onNewIntent(intent); receive(intent); }
    @Override protected void onResume() { super.onResume(); showFiles(); handler.post(refresh); }
    @Override protected void onPause() { handler.removeCallbacks(refresh); super.onPause(); }
    @Override protected void onSaveInstanceState(Bundle out) { super.onSaveInstanceState(out); out.putString("url",url.getText().toString()); out.putInt("mode",modes.getCheckedRadioButtonId()); if(exportFile!=null)out.putString("export",exportFile.getAbsolutePath()); }
    private void showFiles() {
        files.removeAllViews(); File[] all=DownloadService.folder(this).listFiles(f -> f.isFile() && !f.getName().endsWith(".part") && !f.getName().endsWith(".ytdl") && !f.getName().contains(".part-Frag"));
        if(all==null || all.length==0) { files.addView(text("Your completed downloads will appear here.",14)); return; }
        Arrays.sort(all,Comparator.comparingLong(File::lastModified).reversed());
        for(File file:all) { gap(files,12); TextView name=text(file.getName(),15); files.addView(name);
            Button share=button("Share / open",files); share.setOnClickListener(v -> share(file));
            Button save=button("Save a copy…",files); save.setOnClickListener(v -> { exportFile=file; Intent pick=new Intent(Intent.ACTION_CREATE_DOCUMENT).addCategory(Intent.CATEGORY_OPENABLE).setType(mime(file)).putExtra(Intent.EXTRA_TITLE,file.getName()); startActivityForResult(pick,10); });
        }
    }
    private String mime(File file) { String ext=android.webkit.MimeTypeMap.getFileExtensionFromUrl(file.getName()); String type=android.webkit.MimeTypeMap.getSingleton().getMimeTypeFromExtension(ext.toLowerCase(Locale.ROOT)); return type==null?"application/octet-stream":type; }
    private void share(File file) { Uri uri=FileProvider.getUriForFile(this,getPackageName()+".files",file); Intent intent=new Intent(Intent.ACTION_SEND).setType(mime(file)).putExtra(Intent.EXTRA_STREAM,uri).addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION); intent.setClipData(ClipData.newRawUri("Blaze download",uri)); startActivity(Intent.createChooser(intent,"Share your download")); }
    @Override protected void onActivityResult(int code,int result,Intent data) {
        super.onActivityResult(code,result,data);
        if(code==10 && result==RESULT_OK && data!=null && exportFile!=null) {
            File source=exportFile; Uri destination=data.getData();
            new Thread(() -> { try(InputStream in=new FileInputStream(source); OutputStream out=getContentResolver().openOutputStream(destination)) { if(out==null)throw new IOException("Cannot open destination"); byte[] buf=new byte[65536]; int n; while((n=in.read(buf))!=-1)out.write(buf,0,n); runOnUiThread(() -> Toast.makeText(this,"Copy saved",Toast.LENGTH_SHORT).show()); } catch(Exception e) { runOnUiThread(() -> Toast.makeText(this,"Could not save copy. Try another folder.",Toast.LENGTH_LONG).show()); } },"BlazeExport").start();
        }
    }
    private void about() { try { String content=readNotice(); new AlertDialog.Builder(this).setTitle("Blaze · Android preview").setMessage(content).setPositiveButton("Close",null).show(); }catch(IOException e){Toast.makeText(this,"© 2026 Brooth-C",Toast.LENGTH_SHORT).show();} }
    private String readNotice() throws IOException {
        try (InputStream in=getAssets().open("NOTICES.txt"); ByteArrayOutputStream out=new ByteArrayOutputStream()) {
            byte[] buffer=new byte[4096]; int count;
            while((count=in.read(buffer))!=-1)out.write(buffer,0,count);
            return out.toString("UTF-8");
        }
    }
    private TextView text(String value,int size) { TextView v=new TextView(this); v.setText(value); v.setTextSize(size); v.setTextColor(size<=14?Color.rgb(168,177,197):Color.WHITE); v.setPadding(0,dp(6),0,dp(6)); return v; }
    private Button button(String value,LinearLayout parent) { Button v=new Button(this); v.setText(value); v.setAllCaps(false); v.setTextColor(orange); v.setMinHeight(dp(48)); parent.addView(v,new LinearLayout.LayoutParams(-1,-2)); return v; }
    private GradientDrawable card(){GradientDrawable d=new GradientDrawable();d.setColor(Color.rgb(29,35,49));d.setCornerRadius(dp(12));return d;}
    private void gap(LinearLayout root,int size){View v=new View(this);root.addView(v,new LinearLayout.LayoutParams(1,dp(size)));}
    private int dp(int n){return Math.round(n*getResources().getDisplayMetrics().density);}
}

