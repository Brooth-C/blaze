package com.brooth.blaze;

import android.Manifest;
import android.app.*;
import android.content.*;
import android.content.res.ColorStateList;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.net.Uri;
import android.os.*;
import android.view.*;
import android.widget.*;
import androidx.core.content.FileProvider;
import org.json.JSONObject;
import java.io.*;
import java.util.*;

public class MainActivity extends Activity {
    private EditText url;
    private RadioGroup modes;
    private Spinner quality,audio;
    private CheckBox playlist;
    private TextView state;
    private ProgressBar bar;
    private LinearLayout items;
    private Button stop,pause;
    private JobStore store;
    private final Handler handler=new Handler(Looper.getMainLooper());
    private String rendered="",exportPath="",exportToken="";
    private boolean copyRequested;
    private int filter;
    private final int orange=Color.rgb(255,140,66),background=Color.rgb(16,19,28);
    private final String[] qualityKeys={"best","2160","1440","1080","720","480","360"};
    private final String[] audioKeys={"original","mp3","m4a","wav","flac"};
    private final Runnable refresh=new Runnable() {
        @Override public void run() {
            state.setText(DownloadService.status);
            bar.setIndeterminate(DownloadService.busy&&DownloadService.progress<0);
            if(DownloadService.progress>=0)bar.setProgress((int)DownloadService.progress);
            stop.setEnabled(!DownloadService.activeId.isEmpty());pause.setEnabled(DownloadService.busy);
            renderJobs();handler.postDelayed(this,1000);
        }
    };
    @Override public void onCreate(Bundle saved) {
        super.onCreate(saved);store=new JobStore(this);
        if(!DownloadService.busy)store.recoverInterrupted();
        ScrollView scroll=new ScrollView(this);scroll.setBackgroundColor(background);
        LinearLayout root=new LinearLayout(this);root.setOrientation(LinearLayout.VERTICAL);root.setPadding(dp(20),dp(20),dp(20),dp(28));scroll.addView(root);setContentView(scroll);
        if(Build.VERSION.SDK_INT>=35)scroll.setOnApplyWindowInsetsListener((view,insets)->{android.graphics.Insets safe=insets.getInsets(WindowInsets.Type.systemBars());view.setPadding(safe.left,safe.top,safe.right,safe.bottom);return insets;});
        LinearLayout brand=new LinearLayout(this);brand.setGravity(Gravity.CENTER_VERTICAL);
        ImageView logo=new ImageView(this);logo.setImageResource(R.drawable.blaze_logo);logo.setContentDescription("Blaze logo");brand.addView(logo,new LinearLayout.LayoutParams(dp(52),dp(52)));
        TextView title=text("Blaze",30);title.setTypeface(null,Typeface.BOLD);brand.addView(title);root.addView(brand);
        root.addView(text("Download. Convert. Keep.",16));gap(root,18);
        TextView label=text("Link",13);label.setLabelFor(R.id.url_input);root.addView(label);
        url=new EditText(this);url.setId(R.id.url_input);url.setSingleLine(true);url.setTextColor(Color.WHITE);url.setHintTextColor(Color.rgb(168,177,197));url.setHint("Paste an HTTPS link");url.setInputType(android.text.InputType.TYPE_CLASS_TEXT|android.text.InputType.TYPE_TEXT_VARIATION_URI);url.setPadding(dp(14),dp(10),dp(14),dp(10));url.setBackground(card());root.addView(url);
        modes=new RadioGroup(this);modes.setId(R.id.download_mode);modes.setOrientation(RadioGroup.HORIZONTAL);
        for(int i=0;i<2;i++){RadioButton b=new RadioButton(this);b.setId(i==0?R.id.video_mode:R.id.audio_mode);b.setText(i==0?"Video":"Audio");b.setTextColor(Color.WHITE);modes.addView(b);}modes.check(R.id.video_mode);root.addView(modes);
        root.addView(text("Maximum video quality",13));quality=spinner(new String[]{"Best available","2160p (4K)","1440p","1080p","720p","480p","360p"},root);quality.setId(R.id.quality_choice);
        root.addView(text("Audio format",13));audio=spinner(new String[]{"Original audio","MP3 · 192 kbps","M4A","WAV","FLAC"},root);audio.setId(R.id.audio_choice);
        modes.setOnCheckedChangeListener((group,id)->{quality.setEnabled(id==R.id.video_mode);audio.setEnabled(id==R.id.audio_mode);});audio.setEnabled(false);
        playlist=new CheckBox(this);playlist.setId(R.id.playlist_choice);playlist.setText("Queue a playlist (up to 200 items)");playlist.setTextColor(Color.WHITE);root.addView(playlist);
        Button add=button("Add to queue",root);add.setId(R.id.add_queue);add.setOnClickListener(v->enqueue());
        gap(root,12);state=text(DownloadService.status,15);root.addView(state);
        bar=new ProgressBar(this,null,android.R.attr.progressBarStyleHorizontal);bar.setMax(100);root.addView(bar);
        LinearLayout controls=new LinearLayout(this);controls.setOrientation(LinearLayout.HORIZONTAL);root.addView(controls);
        stop=smallButton("Stop item",controls);stop.setOnClickListener(v->control("CANCEL_CURRENT"));
        pause=smallButton("Pause queue",controls);pause.setOnClickListener(v->control("PAUSE"));
        Button resume=button("Resume queue",root);resume.setOnClickListener(v->resume());
        gap(root,18);LinearLayout tabs=new LinearLayout(this);root.addView(tabs);
        String[] names={"Queue","History","Files"};for(int i=0;i<3;i++){final int chosen=i;Button tab=smallButton(names[i],tabs);tab.setOnClickListener(v->{filter=chosen;rendered="";renderJobs();});}
        items=new LinearLayout(this);items.setOrientation(LinearLayout.VERTICAL);root.addView(items);
        gap(root,18);root.addView(text("Save a copy to keep files outside Blaze. Uninstalling removes app files. Android may pause background jobs; retry interrupted items.",12));
        Button about=button("About & help",root);about.setOnClickListener(v->about());
        SharedPreferences preferences=getPreferences(MODE_PRIVATE);
        quality.setSelection(preferences.getInt("quality",0));audio.setSelection(preferences.getInt("audio",1));
        if(saved!=null){url.setText(saved.getString("url",""));modes.check(saved.getInt("mode",R.id.video_mode));quality.setSelection(saved.getInt("quality",0));audio.setSelection(saved.getInt("audio",1));playlist.setChecked(saved.getBoolean("playlist"));filter=saved.getInt("filter");exportPath=saved.getString("export","");exportToken=saved.getString("exportToken","");copyRequested=saved.getBoolean("copyRequested");}
        else receive(getIntent());
    }
    private void enqueue() {
        String value=url.getText().toString().trim();Uri link=Uri.parse(value);
        if(value.length()>8192||!"https".equalsIgnoreCase(link.getScheme())||link.getHost()==null||link.getUserInfo()!=null||value.matches("(?s).*\\p{Cntrl}.*")){url.setError("Paste a complete HTTPS link without login credentials");return;}
        try {
            JSONObject options=new JSONObject().put("quality",qualityKeys[quality.getSelectedItemPosition()]).put("audio",audioKeys[audio.getSelectedItemPosition()]).put("playlist",playlist.isChecked());
            store.enqueue(value,modes.getCheckedRadioButtonId()==R.id.audio_mode?"audio":"video",options.toString(),link.getHost());
            getPreferences(MODE_PRIVATE).edit().putInt("quality",quality.getSelectedItemPosition()).putInt("audio",audio.getSelectedItemPosition()).apply();
            filter=0;rendered="";renderJobs();if(getSharedPreferences("queue",MODE_PRIVATE).getBoolean("paused",false))message("Added. Your queue is paused.");else resume();
        }catch(Exception error){message(error.getMessage()==null?"Could not queue this item":error.getMessage());}
    }
    private void resume() {
        store.resumePending();
        if(!store.hasQueued()&&!DownloadService.busy){message("No queued items. Retry stopped or failed items from History.");return;}
        if(Build.VERSION.SDK_INT>=33&&checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS)!=android.content.pm.PackageManager.PERMISSION_GRANTED&&!getPreferences(MODE_PRIVATE).getBoolean("notificationAsked",false)){getPreferences(MODE_PRIVATE).edit().putBoolean("notificationAsked",true).apply();requestPermissions(new String[]{Manifest.permission.POST_NOTIFICATIONS},2);}
        try {Intent intent=new Intent(this,DownloadService.class).setAction("RESUME");if(Build.VERSION.SDK_INT>=26)startForegroundService(intent);else startService(intent);}
        catch(RuntimeException error){message("Android could not start the queue. Your items are saved; open Blaze and try again.");}
    }
    private void control(String action){try{startService(new Intent(this,DownloadService.class).setAction(action));}catch(RuntimeException error){message("Open Blaze again to manage the queue.");}}
    private void renderJobs() {
        List<JobStore.Job> jobs=store.list();StringBuilder key=new StringBuilder().append(filter);
        for(JobStore.Job job:jobs)key.append(job.id).append(job.state).append(job.title).append(job.path).append(job.error);
        if(key.toString().equals(rendered))return;rendered=key.toString();items.removeAllViews();int count=0;
        for(JobStore.Job job:jobs){boolean pending=Arrays.asList("queued","running","paused","interrupted").contains(job.state);if(filter==0&&!pending||filter==1&&pending||filter==2&&!"complete".equals(job.state))continue;count++;
            LinearLayout panel=new LinearLayout(this);panel.setOrientation(LinearLayout.VERTICAL);panel.setPadding(dp(12),dp(10),dp(12),dp(10));panel.setBackground(card());gap(items,10);items.addView(panel);
            TextView title=text(job.title,16);title.setTypeface(null,Typeface.BOLD);panel.addView(title);panel.addView(text(job.state.toUpperCase(Locale.ROOT)+" · "+job.mode,12));
            if(!job.error.isEmpty())panel.addView(text(job.error,13));
            if(Arrays.asList("queued","paused","interrupted").contains(job.state)){button("Remove from queue",panel).setOnClickListener(v->{store.removeQueued(job.id);rendered="";renderJobs();});}
            if(Arrays.asList("failed","stopped","interrupted").contains(job.state)){button("Retry",panel).setOnClickListener(v->{try{store.retry(job.id);filter=0;rendered="";renderJobs();resume();}catch(RuntimeException error){message(error.getMessage()==null?"Could not retry":error.getMessage());}});}
            if("complete".equals(job.state)){
                File file=new File(job.path);panel.addView(text(file.exists()?String.format(Locale.ROOT,"%.1f MB · %s",file.length()/1048576.0,file.getName()):"File no longer available",12));
                if(file.exists()){
                    button("Share / open",panel).setOnClickListener(v->share(file));
                    button("Save a copy…",panel).setOnClickListener(v->export(file,job.title));
                    button("Delete local file",panel).setOnClickListener(v->new AlertDialog.Builder(this).setTitle("Delete this app file?").setMessage("Exported copies are kept. This removes the file stored inside Blaze.").setNegativeButton("Keep",null).setPositiveButton("Delete",(d,w)->{try{store.deleteCompleted(job.id,DownloadService.folder(this));rendered="";renderJobs();}catch(IOException error){message("Could not delete this file");}}).show());
                }
            }
        }
        if(count==0)items.addView(text(filter==0?"Your queue is empty.":filter==1?"Completed and stopped items will appear here.":"Completed files will appear here.",14));
    }
    private void receive(Intent intent){if(Intent.ACTION_SEND.equals(intent.getAction())){String value=intent.getStringExtra(Intent.EXTRA_TEXT);if(value!=null){java.util.regex.Matcher m=java.util.regex.Pattern.compile("https://[^\\s<>]+",java.util.regex.Pattern.CASE_INSENSITIVE).matcher(value);if(m.find())url.setText(m.group().replaceAll("[).,;]+$",""));}}}
    @Override protected void onNewIntent(Intent intent){super.onNewIntent(intent);setIntent(intent);receive(intent);}
    @Override protected void onResume(){super.onResume();rendered="";handler.removeCallbacks(refresh);handler.post(refresh);}
    @Override protected void onPause(){handler.removeCallbacks(refresh);super.onPause();}
    @Override protected void onDestroy(){handler.removeCallbacks(refresh);if(!isChangingConfigurations()&&!copyRequested&&!exportToken.isEmpty())ExportService.abandon(exportToken);store.close();super.onDestroy();}
    @Override protected void onSaveInstanceState(Bundle out){super.onSaveInstanceState(out);out.putString("url",url.getText().toString());out.putInt("mode",modes.getCheckedRadioButtonId());out.putInt("quality",quality.getSelectedItemPosition());out.putInt("audio",audio.getSelectedItemPosition());out.putBoolean("playlist",playlist.isChecked());out.putInt("filter",filter);out.putString("export",exportPath);out.putString("exportToken",exportToken);out.putBoolean("copyRequested",copyRequested);}
    private String mime(File file){String name=file.getName();String ext=name.substring(name.lastIndexOf('.')+1).toLowerCase(Locale.ROOT);String value=android.webkit.MimeTypeMap.getSingleton().getMimeTypeFromExtension(ext);return value==null?"application/octet-stream":value;}
    private void share(File file){try{Uri uri=FileProvider.getUriForFile(this,getPackageName()+".files",file);Intent intent=new Intent(Intent.ACTION_SEND).setType(mime(file)).putExtra(Intent.EXTRA_STREAM,uri).addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);intent.setClipData(ClipData.newRawUri("Blaze download",uri));startActivity(Intent.createChooser(intent,"Share your download"));}catch(RuntimeException error){message("No app could open this file.");}}
    private void export(File file,String title){exportToken=ExportService.reserve();if(exportToken.isEmpty()){message("Finish the current copy first.");return;}copyRequested=false;exportPath=file.getAbsolutePath();String name=title.replaceAll("[^\\p{L}\\p{N} ._-]","_");if(name.length()>80)name=name.substring(0,80);String ext=file.getName().substring(file.getName().lastIndexOf('.'));try{startActivityForResult(new Intent(Intent.ACTION_CREATE_DOCUMENT).addCategory(Intent.CATEGORY_OPENABLE).setType(mime(file)).putExtra(Intent.EXTRA_TITLE,name+ext),10);}catch(ActivityNotFoundException error){ExportService.abandon(exportToken);exportToken="";message("No folder picker is available on this device.");}}
    @Override protected void onActivityResult(int code,int result,Intent data){super.onActivityResult(code,result,data);if(code!=10)return;if(result==RESULT_OK&&data!=null&&data.getData()!=null&&!exportPath.isEmpty()){if(!ExportService.owns(exportToken))exportToken=ExportService.reserve();if(exportToken.isEmpty()){message("Another copy is running. Remove this empty destination and retry later.");return;}Intent intent=new Intent(this,ExportService.class).putExtra("path",exportPath).putExtra("uri",data.getData().toString()).putExtra("token",exportToken);try{copyRequested=true;if(Build.VERSION.SDK_INT>=26)startForegroundService(intent);else startService(intent);}catch(RuntimeException error){copyRequested=false;ExportService.abandon(exportToken);message("Copy could not start. Try again with Blaze open.");}}else ExportService.abandon(exportToken);exportPath="";exportToken="";}
    private void about(){try{String content=readNotice();new AlertDialog.Builder(this).setTitle("Blaze 0.2.0 · Android preview").setMessage(content).setPositiveButton("Close",null).show();}catch(IOException error){message("Blaze 0.2.0 · © 2026 Brooth-C");}}
    private String readNotice()throws IOException{try(InputStream in=getAssets().open("NOTICES.txt");ByteArrayOutputStream out=new ByteArrayOutputStream()){byte[] buffer=new byte[4096];int count;while((count=in.read(buffer))!=-1)out.write(buffer,0,count);return out.toString("UTF-8");}}
    private Spinner spinner(String[] values,LinearLayout root){Spinner v=new Spinner(this);ArrayAdapter<String> adapter=new ArrayAdapter<>(this,android.R.layout.simple_spinner_item,values);adapter.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item);v.setAdapter(adapter);root.addView(v,new LinearLayout.LayoutParams(-1,dp(48)));return v;}
    private TextView text(String value,int size){TextView v=new TextView(this);v.setText(value);v.setTextSize(size);v.setTextColor(size<=14?Color.rgb(168,177,197):Color.WHITE);v.setPadding(0,dp(5),0,dp(5));return v;}
    private Button makeButton(String value){Button v=new Button(this);v.setText(value);v.setAllCaps(false);v.setTextColor(new ColorStateList(new int[][]{new int[]{-android.R.attr.state_enabled},new int[]{}},new int[]{Color.GRAY,orange}));v.setMinHeight(dp(48));return v;}
    private Button button(String value,LinearLayout parent){Button v=makeButton(value);parent.addView(v,new LinearLayout.LayoutParams(-1,-2));return v;}
    private Button smallButton(String value,LinearLayout parent){Button v=makeButton(value);parent.addView(v,new LinearLayout.LayoutParams(0,-2,1));return v;}
    private GradientDrawable card(){GradientDrawable d=new GradientDrawable();d.setColor(Color.rgb(29,35,49));d.setCornerRadius(dp(12));return d;}
    private void gap(LinearLayout root,int size){root.addView(new View(this),new LinearLayout.LayoutParams(1,dp(size)));}
    private int dp(int n){return Math.round(n*getResources().getDisplayMetrics().density);}
    private void message(String value){Toast.makeText(this,value,Toast.LENGTH_LONG).show();}
}
