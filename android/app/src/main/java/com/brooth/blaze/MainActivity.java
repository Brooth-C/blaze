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
    private LinearLayout items,downloadComposer,queuePanel,paging,brandHeader,miniPlayer,historySegments;
    private FrameLayout contentHost;
    private ExploreView explore;
    private Button exploreTab,studioTab,queueTab;
    private ImageView miniArt;
    private TextView miniTitle,miniCreator;
    private ImageButton miniToggle;
    private ProgressBar miniProgress;
    private String destination="explore",miniImageKey="";
    private final PlaybackController.Listener playbackListener=()->renderMiniPlayer();
    private ScrollView contentScroll;
    private BlazeUi ui;
    private TextView sectionSubtitle;
    private Button resumeQueue;
    private TextView sectionTitle;
    private final Button[] sectionTabs=new Button[3];
    private Button stop,pause,previousPage,nextPage,openFile;
    private TextView pageLabel;
    private JobStore store;
    private final Handler handler=new Handler(Looper.getMainLooper());
    private String rendered="",exportPath="",exportToken="";
    private boolean copyRequested;
    private int filter,page;
    private int orange=0xffc94819,background=Color.WHITE,foreground=0xff1d1d1f,muted=0xff68686f,surface=0xfff5f5f7,selection=0xffe5e6e9;
    private final String[] qualityKeys={"best","2160","1440","1080","720","480","360"};
    private final String[] audioKeys={"original","mp3","m4a","wav","flac"};
    private final Runnable refresh=new Runnable() {
        @Override public void run() {
            state.setText(DownloadService.status);
            bar.setIndeterminate(DownloadService.busy&&DownloadService.progress<0);
            if(DownloadService.progress>=0)bar.setProgress((int)DownloadService.progress);
            stop.setEnabled(!DownloadService.activeId.isEmpty());pause.setEnabled(DownloadService.busy);
            renderJobs();renderMiniPlayer();DownloadCoordinator.offerReadyStudio(MainActivity.this);handler.postDelayed(this,1000);
        }
    };
    @Override public void onCreate(Bundle saved) {
        BlazeUi.apply(this);
        super.onCreate(saved);
        ui=new BlazeUi(this);orange=ui.accent;background=ui.background;foreground=ui.text;muted=ui.secondary;surface=ui.surface;selection=ui.softAccent;
        store=new JobStore(this);
        if(!DownloadService.busy)store.recoverInterrupted();
        if(!getPreferences(MODE_PRIVATE).getBoolean("legacyImported",false)){try{store.importLegacyFiles(DownloadService.folder(this));getPreferences(MODE_PRIVATE).edit().putBoolean("legacyImported",true).apply();}catch(IOException ignored){/* Retry after storage becomes available. */}}

        LinearLayout shell=ui.column();shell.setTag("blaze_shell");shell.setBackgroundColor(background);setContentView(shell);
        if(Build.VERSION.SDK_INT>=35)shell.setOnApplyWindowInsetsListener((view,insets)->{android.graphics.Insets safe=insets.getInsets(WindowInsets.Type.systemBars()|WindowInsets.Type.ime());view.setPadding(safe.left,safe.top,safe.right,safe.bottom);return insets;});
        LinearLayout brand=new LinearLayout(this);brandHeader=brand;brand.setGravity(Gravity.CENTER_VERTICAL);brand.setPadding(dp(20),dp(4),dp(16),dp(4));
        ImageView logo=new ImageView(this);logo.setId(R.id.brand_logo);logo.setLayerType(View.LAYER_TYPE_SOFTWARE,null);logo.setImageResource(R.drawable.blaze_brand_mark);logo.setScaleType(ImageView.ScaleType.FIT_CENTER);logo.setBackgroundColor(Color.TRANSPARENT);logo.setContentDescription("Blaze logo");brand.addView(logo,new LinearLayout.LayoutParams(dp(30),dp(34)));
        TextView brandName=ui.heading("Blaze",21);LinearLayout.LayoutParams brandLabel=new LinearLayout.LayoutParams(0,-2,1);brandLabel.setMarginStart(dp(9));brand.addView(brandName,brandLabel);
        Button about=ui.button("",false);about.setCompoundDrawablesWithIntrinsicBounds(null,null,ui.icon("more",foreground),null);about.setContentDescription("About Blaze and help");about.setOnClickListener(v->about());brand.addView(about,new LinearLayout.LayoutParams(dp(52),dp(48)));shell.addView(brand);

        contentHost=new FrameLayout(this);shell.addView(contentHost,new LinearLayout.LayoutParams(-1,0,1));
        contentScroll=new ScrollView(this);contentScroll.setFillViewport(true);contentScroll.setClipToPadding(false);contentScroll.setVerticalScrollBarEnabled(false);contentHost.addView(contentScroll,new FrameLayout.LayoutParams(-1,-1));
        LinearLayout root=ui.column();root.setPadding(dp(24),dp(8),dp(24),dp(28));contentScroll.addView(root);
        sectionTitle=ui.heading("Downloads",34);if(Build.VERSION.SDK_INT>=28)sectionTitle.setAccessibilityHeading(true);root.addView(sectionTitle);
        sectionSubtitle=text("Keep what moves you.",15);root.addView(sectionSubtitle);gap(root,16);
        historySegments=new LinearLayout(this);historySegments.setPadding(0,0,0,dp(12));root.addView(historySegments);
        queueTab=ui.button("Queue",false);queueTab.setTag("nav_queue");historySegments.addView(queueTab,new LinearLayout.LayoutParams(0,-2,1));
        Button historyTab=ui.button("History",false);historyTab.setTag("nav_history");sectionTabs[1]=historyTab;historySegments.addView(historyTab,new LinearLayout.LayoutParams(0,-2,1));
        queueTab.setOnClickListener(v->{filter=0;page=0;rendered="";renderJobs();});historyTab.setOnClickListener(v->{filter=1;page=0;rendered="";renderJobs();});
        downloadComposer=ui.card();downloadComposer.setPadding(dp(20),dp(20),dp(20),dp(20));root.addView(downloadComposer);
        TextView composerTitle=ui.heading("Save from a link",20);downloadComposer.addView(composerTitle);gap(downloadComposer,14);
        TextView label=text("Link",12);label.setLabelFor(R.id.url_input);downloadComposer.addView(label);
        url=new EditText(this);url.setId(R.id.url_input);url.setSingleLine(true);url.setHint("Paste an HTTPS link");url.setInputType(android.text.InputType.TYPE_CLASS_TEXT|android.text.InputType.TYPE_TEXT_VARIATION_URI);url.setImeOptions(android.view.inputmethod.EditorInfo.IME_ACTION_DONE);ui.styleInput(url);downloadComposer.addView(url,new LinearLayout.LayoutParams(-1,-2));
        gap(downloadComposer,16);modes=new RadioGroup(this);modes.setId(R.id.download_mode);modes.setOrientation(RadioGroup.HORIZONTAL);modes.setBackground(ui.shape(ui.background,14));modes.setPadding(dp(4),dp(4),dp(4),dp(4));
        for(int i=0;i<2;i++){RadioButton b=new RadioButton(this);b.setId(i==0?R.id.video_mode:R.id.audio_mode);b.setText(i==0?"Video":"Audio");b.setTextSize(14);b.setGravity(Gravity.CENTER);b.setButtonDrawable((android.graphics.drawable.Drawable)null);b.setMinHeight(dp(48));b.setPadding(dp(10),dp(8),dp(10),dp(8));modes.addView(b,new RadioGroup.LayoutParams(0,-2,1));}
        downloadComposer.addView(modes);modes.check(R.id.video_mode);styleModes();gap(downloadComposer,12);
        TextView qualityLabel=text("Video quality",12);downloadComposer.addView(qualityLabel);quality=spinner(new String[]{"Best available","2160p (4K)","1440p","1080p","720p","480p","360p"},downloadComposer);quality.setId(R.id.quality_choice);qualityLabel.setLabelFor(R.id.quality_choice);
        TextView audioLabel=text("Audio format",12);downloadComposer.addView(audioLabel);audio=spinner(new String[]{"Original audio","MP3 · 192 kbps","M4A","WAV","FLAC"},downloadComposer);audio.setId(R.id.audio_choice);audioLabel.setLabelFor(R.id.audio_choice);
        modes.setOnCheckedChangeListener((group,id)->{boolean video=id==R.id.video_mode;quality.setVisibility(video?View.VISIBLE:View.GONE);qualityLabel.setVisibility(video?View.VISIBLE:View.GONE);audio.setVisibility(video?View.GONE:View.VISIBLE);audioLabel.setVisibility(video?View.GONE:View.VISIBLE);styleModes();});audio.setVisibility(View.GONE);audioLabel.setVisibility(View.GONE);
        gap(downloadComposer,8);playlist=new CheckBox(this);playlist.setId(R.id.playlist_choice);playlist.setText("Include playlist");playlist.setTextSize(14);playlist.setTextColor(foreground);playlist.setMinHeight(dp(48));playlist.setButtonTintList(new ColorStateList(new int[][]{new int[]{android.R.attr.state_checked},new int[]{}},new int[]{orange,muted}));playlist.setContentDescription("Include playlist, up to 200 items");downloadComposer.addView(playlist);
        gap(downloadComposer,12);Button add=ui.button("Add to queue",true);add.setId(R.id.add_queue);downloadComposer.addView(add,new LinearLayout.LayoutParams(-1,-2));add.setOnClickListener(v->enqueue());
        url.setOnEditorActionListener((view,action,event)->{if(action==android.view.inputmethod.EditorInfo.IME_ACTION_DONE){enqueue();return true;}return false;});

        gap(root,24);queuePanel=ui.card();queuePanel.setTag("queue_panel");root.addView(queuePanel);queuePanel.addView(ui.heading("Your queue",18));
        state=text(DownloadService.status,13);state.setAccessibilityLiveRegion(View.ACCESSIBILITY_LIVE_REGION_POLITE);queuePanel.addView(state);
        bar=new ProgressBar(this,null,android.R.attr.progressBarStyleHorizontal);bar.setMax(100);bar.setProgressTintList(ColorStateList.valueOf(orange));bar.setIndeterminateTintList(ColorStateList.valueOf(orange));queuePanel.addView(bar,new LinearLayout.LayoutParams(-1,dp(8)));gap(queuePanel,12);
        LinearLayout controls=new LinearLayout(this);queuePanel.addView(controls);stop=smallButton("Stop item",controls);stop.setOnClickListener(v->{try{startService(new Intent(this,DownloadService.class).setAction("CANCEL_CURRENT").putExtra("job",DownloadService.activeId));}catch(RuntimeException error){message("Open Blaze again to manage the queue.");}});pause=smallButton("Pause queue",controls);pause.setOnClickListener(v->control("PAUSE"));
        resumeQueue=button("Resume queue",queuePanel);resumeQueue.setTag("resume_queue");resumeQueue.setOnClickListener(v->resume());
        openFile=button("Open a file",root);openFile.setCompoundDrawablesWithIntrinsicBounds(ui.icon("folder",orange),null,null,null);openFile.setCompoundDrawablePadding(dp(10));openFile.setVisibility(View.GONE);openFile.setOnClickListener(v->pickFile(11));
        items=ui.column();root.addView(items);paging=new LinearLayout(this);root.addView(paging);previousPage=smallButton("Previous",paging);nextPage=smallButton("Next",paging);pageLabel=text("",12);root.addView(pageLabel);
        previousPage.setOnClickListener(v->{page=Math.max(0,page-1);rendered="";renderJobs();});nextPage.setOnClickListener(v->{page++;rendered="";renderJobs();});
        gap(root,20);TextView localNote=text("Your files stay on this device. Save a copy to keep them after uninstalling Blaze.",12);localNote.setLineSpacing(dp(3),1);root.addView(localNote);

        explore=new ExploreView(this,new ExploreView.Actions(){
            @Override public void onPlay(DiscoveryItem item,List<DiscoveryItem> queue){playDiscovery(item,queue);}
            @Override public void onDownload(DiscoveryItem item,boolean forStudio){DownloadCoordinator.showOptions(MainActivity.this,item,forStudio);}
            @Override public void onOpenPlayer(){openNowPlaying();}
            @Override public void onSettings(){discoverySettings();}
        });contentHost.addView(explore,new FrameLayout.LayoutParams(-1,-1));
        createMiniPlayer(shell);
        shell.addView(ui.divider(),new LinearLayout.LayoutParams(-1,dp(1)));LinearLayout navigation=new LinearLayout(this);navigation.setTag("bottom_navigation");navigation.setGravity(Gravity.CENTER_VERTICAL);navigation.setPadding(dp(8),0,dp(8),0);navigation.setBackgroundColor(background);shell.addView(navigation);
        exploreTab=navigationButton("Explore","explore");exploreTab.setTag("nav_explore");navigation.addView(exploreTab,new LinearLayout.LayoutParams(0,-2,1));exploreTab.setOnClickListener(v->showDestination("explore"));
        sectionTabs[0]=navigationButton("Downloads","download");sectionTabs[0].setTag("nav_downloads");navigation.addView(sectionTabs[0],new LinearLayout.LayoutParams(0,-2,1));sectionTabs[0].setOnClickListener(v->{filter=0;page=0;showDestination("downloads");});
        sectionTabs[2]=navigationButton("Library","library");sectionTabs[2].setTag("nav_library");navigation.addView(sectionTabs[2],new LinearLayout.LayoutParams(0,-2,1));sectionTabs[2].setOnClickListener(v->{page=0;showDestination("library");});
        studioTab=navigationButton("Studio","studio");studioTab.setId(R.id.find_chords);studioTab.setTag("nav_studio");studioTab.setContentDescription("Music Studio, import an audio or video file");navigation.addView(studioTab,new LinearLayout.LayoutParams(0,-2,1));studioTab.setOnClickListener(v->pickFile(12));
        SharedPreferences preferences=getPreferences(MODE_PRIVATE);
        quality.setSelection(preferences.getInt("quality",0));audio.setSelection(preferences.getInt("audio",1));
        if(saved!=null){url.setText(saved.getString("url",""));modes.check(saved.getInt("mode",R.id.video_mode));quality.setSelection(saved.getInt("quality",0));audio.setSelection(saved.getInt("audio",1));playlist.setChecked(saved.getBoolean("playlist"));filter=saved.getInt("filter");page=saved.getInt("page");exportPath=saved.getString("export","");exportToken=saved.getString("exportToken","");copyRequested=saved.getBoolean("copyRequested");}
        if(saved!=null){destination=saved.getString("destination",filter==2?"library":"downloads");explore.restoreState(saved);}
        else {destination=preferences.getString("lastDestination","explore");receive(getIntent());}
        if(saved==null&&getIntent().hasExtra("destination"))destination=getIntent().getStringExtra("destination");
        showDestination(destination);
    }
    private void enqueue() {
        String value=url.getText().toString().trim();Uri link=Uri.parse(value);
        if(value.length()>8192||!"https".equalsIgnoreCase(link.getScheme())||link.getHost()==null||link.getUserInfo()!=null||value.matches("(?s).*\\p{Cntrl}.*")){url.setError("Paste a complete HTTPS link without login credentials");return;}
        try {
            DownloadCoordinator.Result result=DownloadCoordinator.enqueue(this,value,modes.getCheckedRadioButtonId()==R.id.audio_mode?"audio":"video",qualityKeys[quality.getSelectedItemPosition()],audioKeys[audio.getSelectedItemPosition()],playlist.isChecked(),link.getHost());
            getPreferences(MODE_PRIVATE).edit().putInt("quality",quality.getSelectedItemPosition()).putInt("audio",audio.getSelectedItemPosition()).apply();
            filter=0;rendered="";renderJobs();if(result.paused)message("Added. Your queue is paused.");else if(result.complete)message("Already in your library.");else DownloadCoordinator.start(this,result);
        }catch(Exception error){message(error.getMessage()==null?"Could not queue this item":error.getMessage());}
    }
    private void resume() {
        store.resumePending();
        if(!store.hasQueued()&&!DownloadService.busy){message("No queued items. Retry stopped or failed items from History.");return;}
        if(Build.VERSION.SDK_INT>=33&&checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS)!=android.content.pm.PackageManager.PERMISSION_GRANTED&&!getSharedPreferences("queue",MODE_PRIVATE).getBoolean("notificationAsked",false)){getSharedPreferences("queue",MODE_PRIVATE).edit().putBoolean("notificationAsked",true).apply();requestPermissions(new String[]{Manifest.permission.POST_NOTIFICATIONS},2);}
        try {Intent intent=new Intent(this,DownloadService.class).setAction("RESUME");if(Build.VERSION.SDK_INT>=26)startForegroundService(intent);else startService(intent);}
        catch(RuntimeException error){message("Android could not start the queue. Your items are saved; open Blaze and try again.");}
    }
    private void control(String action){try{startService(new Intent(this,DownloadService.class).setAction(action));}catch(RuntimeException error){message("Open Blaze again to manage the queue.");}}
    private void renderJobs() {
        downloadComposer.setVisibility(filter==0?View.VISIBLE:View.GONE);
        sectionTitle.setText(filter==0?"Downloads":filter==1?"History":"Library");
        sectionSubtitle.setText(filter==0?"Keep what moves you.":filter==1?"Every save, in one place.":"Your collection. Always with you.");
        updateNavigation();historySegments.setVisibility(filter==2?View.GONE:View.VISIBLE);
        openFile.setVisibility(filter==2?View.VISIBLE:View.GONE);
        boolean hasPending=store.count(0)>0;boolean active=DownloadService.busy||hasPending;queuePanel.setVisibility(filter==0&&active?View.VISIBLE:View.GONE);stop.setVisibility(DownloadService.activeId.isEmpty()?View.GONE:View.VISIBLE);pause.setVisibility(DownloadService.busy?View.VISIBLE:View.GONE);resumeQueue.setVisibility(!DownloadService.busy&&hasPending?View.VISIBLE:View.GONE);
        int total=store.count(filter);page=Math.max(0,Math.min(page,Math.max(0,(total-1)/50)));previousPage.setEnabled(page>0);nextPage.setEnabled((page+1)*50<total);pageLabel.setText(total==0?"":"Page "+(page+1)+" · "+total+" items");paging.setVisibility(total>50?View.VISIBLE:View.GONE);pageLabel.setVisibility(total>50?View.VISIBLE:View.GONE);
        List<JobStore.Job> jobs=store.page(filter,page*50);StringBuilder key=new StringBuilder().append(filter).append(page).append(total);
        for(JobStore.Job job:jobs)key.append(job.id).append(job.state).append(job.title).append(job.path).append(job.error);
        if(key.toString().equals(rendered))return;rendered=key.toString();items.removeAllViews();int count=0;
        for(JobStore.Job job:jobs){boolean pending=Arrays.asList("queued","running","paused","interrupted").contains(job.state);if(filter==0&&!pending||filter==1&&pending||filter==2&&!"complete".equals(job.state))continue;count++;
            LinearLayout panel=ui.card();gap(items,12);items.addView(panel);
            TextView title=text(job.title,16);title.setTypeface(null,Typeface.BOLD);panel.addView(title);panel.addView(text(job.state.substring(0,1).toUpperCase(Locale.ROOT)+job.state.substring(1)+" · "+(job.mode.equals("audio")?"Audio":"Video"),12));
            if(!job.error.isEmpty())panel.addView(text(job.error,13));
            if(Arrays.asList("queued","paused","interrupted").contains(job.state)){button("Remove item & partial files",panel).setOnClickListener(v->new AlertDialog.Builder(this).setTitle("Remove this queued item?").setMessage("Its partial files inside Blaze will be discarded.").setNegativeButton("Keep",null).setPositiveButton("Remove",(dialog,choice)->new Thread(()->{try{try(JobStore removalStore=new JobStore(getApplicationContext())){removalStore.removeQueued(job.id,DownloadService.folder(getApplicationContext()));}handler.post(()->{if(!isFinishing()&&!isDestroyed()){rendered="";renderJobs();}});}catch(Exception error){handler.post(()->message("Could not remove this item; its files were kept."));}},"BlazeRemove").start()).show());}
            if(Arrays.asList("failed","stopped","interrupted").contains(job.state)){button("Retry",panel).setOnClickListener(v->{try{store.retry(job.id);filter=0;rendered="";renderJobs();resume();}catch(RuntimeException error){message(error.getMessage()==null?"Could not retry":error.getMessage());}});}
            if("complete".equals(job.state)){
                File file=new File(job.path);panel.addView(text(file.exists()?String.format(Locale.ROOT,"%.1f MB · %s",file.length()/1048576.0,file.getName()):"File no longer available",12));
                if(file.exists()){
                    gap(panel,12);LinearLayout mediaActions=new LinearLayout(this);panel.addView(mediaActions);Button play=smallButton("Play",mediaActions);play.setTag("saved_play_"+job.id);ui.styleButton(play,true);play.setOnClickListener(v->play(job.id));Button more=smallButton("More",mediaActions);more.setOnClickListener(v->fileActions(more,file,job));

                }
            }
        }
        if(count==0){
            LinearLayout empty=ui.column();empty.setTag("empty_state");empty.setGravity(Gravity.CENTER);empty.setPadding(dp(18),dp(32),dp(18),dp(20));items.addView(empty);
            ImageView illustration=new ImageView(this);illustration.setImageDrawable(ui.icon(filter==0?"download":filter==1?"clock":"library",muted));illustration.setImportantForAccessibility(View.IMPORTANT_FOR_ACCESSIBILITY_NO);empty.addView(illustration,new LinearLayout.LayoutParams(dp(30),dp(30)));gap(empty,12);
            TextView emptyTitle=ui.heading(filter==0?"Ready when you are":filter==1?"A fresh start":"Make room for your favourites",18);emptyTitle.setGravity(Gravity.CENTER);empty.addView(emptyTitle);
            TextView hint=text(filter==0?"Add a link above. We’ll take it from here.":filter==1?"Completed and stopped downloads appear here.":"Your saved audio and video will live here.\nYou can also open a file from your device.",14);hint.setGravity(Gravity.CENTER);hint.setLineSpacing(dp(3),1);empty.addView(hint);
        }
    }
    private void receive(Intent intent){if(Intent.ACTION_SEND.equals(intent.getAction())){CharSequence shared=intent.getCharSequenceExtra(Intent.EXTRA_TEXT);String value=shared==null?null:shared.toString();if(value!=null){java.util.regex.Matcher m=java.util.regex.Pattern.compile("https://[^\\s<>]+",java.util.regex.Pattern.CASE_INSENSITIVE).matcher(value);if(m.find()){url.setText(m.group().replaceAll("[).,;]+$",""));destination="downloads";filter=0;}}}}
    @Override protected void onNewIntent(Intent intent){super.onNewIntent(intent);setIntent(intent);receive(intent);if(intent.hasExtra("destination"))destination=intent.getStringExtra("destination");showDestination(destination);}
    @Override protected void onResume(){super.onResume();rendered="";PlaybackController.get(this).addListener(playbackListener);if("explore".equals(destination))explore.onResume();handler.removeCallbacks(refresh);handler.post(refresh);}
    @Override protected void onPause(){handler.removeCallbacks(refresh);PlaybackController.get(this).removeListener(playbackListener);explore.onPause();super.onPause();}
    @Override protected void onDestroy(){handler.removeCallbacks(refresh);explore.onDestroy();if(!isChangingConfigurations()&&!copyRequested&&!exportToken.isEmpty())ExportService.abandon(exportToken);store.close();super.onDestroy();}
    @Override public void onBackPressed(){if("explore".equals(destination)&&explore.handleBack())return;if(!"explore".equals(destination)){showDestination("explore");return;}super.onBackPressed();}
    @Override protected void onSaveInstanceState(Bundle out){super.onSaveInstanceState(out);out.putString("url",url.getText().toString());out.putInt("mode",modes.getCheckedRadioButtonId());out.putInt("quality",quality.getSelectedItemPosition());out.putInt("audio",audio.getSelectedItemPosition());out.putBoolean("playlist",playlist.isChecked());out.putInt("filter",filter);out.putInt("page",page);out.putString("export",exportPath);out.putString("exportToken",exportToken);out.putBoolean("copyRequested",copyRequested);out.putString("destination",destination);explore.saveState(out);}
    private String mime(File file){String name=file.getName();String ext=name.substring(name.lastIndexOf('.')+1).toLowerCase(Locale.ROOT);String value=android.webkit.MimeTypeMap.getSingleton().getMimeTypeFromExtension(ext);return value==null?"application/octet-stream":value;}
    private void share(File file){try{Uri uri=FileProvider.getUriForFile(this,getPackageName()+".files",file);Intent intent=new Intent(Intent.ACTION_SEND).setType(mime(file)).putExtra(Intent.EXTRA_STREAM,uri).addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);intent.setClipData(ClipData.newRawUri("Blaze download",uri));startActivity(Intent.createChooser(intent,"Share your download"));}catch(RuntimeException error){message("No app could open this file.");}}
    private void play(String id){try{PlaybackController.get(this).pause();startActivity(new Intent(this,VlcPlayerActivity.class).putExtra("job",id));}catch(RuntimeException error){message("Could not open the Blaze player. Try again.");}}
    private void export(File file,String title){exportToken=ExportService.reserve();if(exportToken.isEmpty()){message("Finish the current copy first.");return;}copyRequested=false;exportPath=file.getAbsolutePath();String name=title.replaceAll("[^\\p{L}\\p{N} ._-]","_");if(name.length()>80)name=name.substring(0,80);String ext=file.getName().substring(file.getName().lastIndexOf('.'));try{startActivityForResult(new Intent(Intent.ACTION_CREATE_DOCUMENT).addCategory(Intent.CATEGORY_OPENABLE).setType(mime(file)).putExtra(Intent.EXTRA_TITLE,name+ext),10);}catch(ActivityNotFoundException error){ExportService.abandon(exportToken);exportToken="";message("No folder picker is available on this device.");}}
    @Override protected void onActivityResult(int code,int result,Intent data){super.onActivityResult(code,result,data);if(code==11||code==12){if(result==RESULT_OK&&data!=null&&data.getData()!=null){try{PlaybackController.get(this).pause();startActivity(new Intent(this,code==12?MusicStudioActivity.class:VlcPlayerActivity.class).setData(data.getData()).addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION));}catch(RuntimeException error){message("Could not open the selected file.");}}return;}if(code!=10)return;if(result==RESULT_OK&&data!=null&&data.getData()!=null&&!exportPath.isEmpty()){if(!ExportService.owns(exportToken))exportToken=ExportService.reserve();if(exportToken.isEmpty()){message("Another copy is running. Remove this empty destination and retry later.");return;}Intent intent=new Intent(this,ExportService.class).putExtra("path",exportPath).putExtra("uri",data.getData().toString()).putExtra("token",exportToken);try{copyRequested=true;if(Build.VERSION.SDK_INT>=26)startForegroundService(intent);else startService(intent);}catch(RuntimeException error){copyRequested=false;ExportService.abandon(exportToken);message("Copy could not start. Try again with Blaze open.");}}else ExportService.abandon(exportToken);exportPath="";exportToken="";}
    private void discoverySettings(){
        new AlertDialog.Builder(this).setTitle("Blaze").setItems(new String[]{"How recommendations work","Reset listening history","About Blaze"},(dialog,choice)->{
            if(choice==0)new AlertDialog.Builder(this).setTitle("Your music, your picks").setMessage("Explore starts with music from YouTube and learns from listening and favourites in Blaze. History and play counts stay on this device. Blaze sends short artist or song searches to YouTube to find new music; no YouTube login is used.").setPositiveButton("Close",null).show();
            else if(choice==1)new AlertDialog.Builder(this).setTitle("Reset listening history?").setMessage("This clears Continue listening and recommendation history. Your saved files and favourites are kept.").setNegativeButton("Cancel",null).setPositiveButton("Reset",(reset,which)->{PlaybackController.get(this).clearListeningHistory();explore.refreshRecommendations();}).show();
            else about();
        }).show();
    }
    private void about(){try{String content=readNotice();new AlertDialog.Builder(this).setTitle("Blaze · Android").setMessage(content).setPositiveButton("Close",null).show();}catch(IOException error){message("Blaze · © 2026 Brooth-C");}}
    private String readNotice()throws IOException{try(InputStream in=getAssets().open("NOTICES.txt");ByteArrayOutputStream out=new ByteArrayOutputStream()){byte[] buffer=new byte[4096];int count;while((count=in.read(buffer))!=-1)out.write(buffer,0,count);return out.toString("UTF-8");}}
    private void pickFile(int request){try{startActivityForResult(new Intent(Intent.ACTION_OPEN_DOCUMENT).addCategory(Intent.CATEGORY_OPENABLE).setType("*/*").putExtra(Intent.EXTRA_MIME_TYPES,new String[]{"audio/*","video/*"}).addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION),request);}catch(ActivityNotFoundException error){message("No file picker is available on this device.");}}
    private void styleModes(){for(int i=0;i<modes.getChildCount();i++){RadioButton choice=(RadioButton)modes.getChildAt(i);boolean selected=choice.isChecked();choice.setTextColor(selected?foreground:muted);choice.setTypeface(null,selected?Typeface.BOLD:Typeface.NORMAL);choice.setBackground(ui.interactiveSurface(selected?ui.surface:ui.background,11));}}
    private Button navigationButton(String value,String icon){Button button=ui.button(value,false);button.setTextSize(10);button.setTextColor(muted);button.setTypeface(null,Typeface.NORMAL);button.setMinHeight(dp(60));button.setMinimumHeight(dp(60));button.setPadding(dp(2),dp(5),dp(2),dp(5));button.setCompoundDrawablePadding(dp(3));button.setCompoundDrawablesWithIntrinsicBounds(null,DiscoveryIcons.get(this,icon,muted),null,null);button.setBackgroundTintList(null);button.setBackground(ui.interactiveSurface(background,0));return button;}
    private void showDestination(String value){
        boolean openStudio="studio".equals(value);
        String chosen="library".equals(value)?"library":"downloads".equals(value)?"downloads":"explore";
        boolean wasExplore=explore.getVisibility()==View.VISIBLE;
        destination=chosen;
        if("library".equals(chosen))filter=2;else if("downloads".equals(chosen)&&filter==2)filter=0;
        boolean discovering="explore".equals(chosen);
        brandHeader.setVisibility(discovering?View.GONE:View.VISIBLE);contentScroll.setVisibility(discovering?View.GONE:View.VISIBLE);explore.setVisibility(discovering?View.VISIBLE:View.GONE);
        if(wasExplore&&!discovering)explore.onPause();else if(!wasExplore&&discovering)explore.onResume();
        getPreferences(MODE_PRIVATE).edit().putString("lastDestination",chosen).apply();rendered="";renderJobs();renderMiniPlayer();
        if(openStudio)pickFile(12);
    }
    private void updateNavigation(){
        Button[] tabs={exploreTab,sectionTabs[0],sectionTabs[2],studioTab};String[] values={"explore","downloads","library","studio"},icons={"explore","download","library","studio"};
        for(int i=0;i<tabs.length;i++){Button tab=tabs[i];if(tab==null)continue;boolean selected=values[i].equals(destination);tab.setSelected(selected);tab.setTextColor(selected?orange:muted);tab.setCompoundDrawablesWithIntrinsicBounds(null,DiscoveryIcons.get(this,icons[i],selected?orange:muted),null,null);}
        if(queueTab!=null){queueTab.setSelected(filter==0);sectionTabs[1].setSelected(filter==1);ui.styleButton(queueTab,filter==0);ui.styleButton(sectionTabs[1],filter==1);}
    }
    private void createMiniPlayer(LinearLayout shell){
        miniPlayer=ui.column();miniPlayer.setTag("mini_player");miniPlayer.setBackground(ui.shape(surface,16));miniPlayer.setPadding(dp(16),dp(6),dp(12),dp(4));shell.addView(miniPlayer,new LinearLayout.LayoutParams(-1,-2));
        LinearLayout row=new LinearLayout(this);row.setGravity(Gravity.CENTER_VERTICAL);row.setOnClickListener(v->openNowPlaying());row.setContentDescription("Open now playing");miniPlayer.addView(row);
        miniArt=new ImageView(this);miniArt.setScaleType(ImageView.ScaleType.CENTER_CROP);miniArt.setBackground(ui.shape(ui.elevated,6));miniArt.setClipToOutline(true);miniArt.setImportantForAccessibility(View.IMPORTANT_FOR_ACCESSIBILITY_NO);row.addView(miniArt,new LinearLayout.LayoutParams(dp(44),dp(44)));
        LinearLayout names=ui.column();names.setPadding(dp(12),0,dp(4),0);row.addView(names,new LinearLayout.LayoutParams(0,-2,1));
        miniTitle=ui.heading("",13);miniTitle.setMaxLines(1);miniTitle.setEllipsize(android.text.TextUtils.TruncateAt.END);names.addView(miniTitle);miniCreator=ui.label("",11,muted);miniCreator.setMaxLines(1);miniCreator.setEllipsize(android.text.TextUtils.TruncateAt.END);names.addView(miniCreator);
        miniToggle=new ImageButton(this);miniToggle.setTag("mini_toggle");miniToggle.setPadding(dp(12),dp(12),dp(12),dp(12));miniToggle.setBackground(ui.interactiveSurface(surface,24));miniToggle.setOnClickListener(v->PlaybackController.get(this).toggle());row.addView(miniToggle,new LinearLayout.LayoutParams(dp(48),dp(48)));
        ImageButton next=new ImageButton(this);next.setTag("mini_next");next.setImageDrawable(DiscoveryIcons.get(this,"next",foreground));next.setContentDescription("Next recording");next.setPadding(dp(12),dp(12),dp(12),dp(12));next.setBackground(ui.interactiveSurface(surface,24));next.setOnClickListener(v->PlaybackController.get(this).next());row.addView(next,new LinearLayout.LayoutParams(dp(48),dp(48)));
        miniProgress=new ProgressBar(this,null,android.R.attr.progressBarStyleHorizontal);miniProgress.setMax(1000);miniProgress.setProgressTintList(ColorStateList.valueOf(orange));miniProgress.setProgressBackgroundTintList(ColorStateList.valueOf(ui.border));LinearLayout.LayoutParams progressSize=new LinearLayout.LayoutParams(-1,dp(2));progressSize.setMarginStart(dp(56));progressSize.setMarginEnd(dp(74));miniPlayer.addView(miniProgress,progressSize);miniPlayer.setVisibility(View.GONE);
    }
    private void renderMiniPlayer(){
        if(miniPlayer==null)return;PlaybackController player=PlaybackController.get(this);DiscoveryItem item=player.current();miniPlayer.setVisibility(item==null?View.GONE:View.VISIBLE);if(item==null)return;
        miniTitle.setText(item.title);miniCreator.setText(player.error().isEmpty()?item.creator:"Tap to retry playback");
        String imageKey=item.key()+item.thumbnail;if(!imageKey.equals(miniImageKey)){miniImageKey=imageKey;DiscoveryArtwork.load(miniArt,item.thumbnail,R.drawable.discovery_sunset);}
        miniToggle.setImageDrawable(DiscoveryIcons.get(this,player.isPlaying()?"pause":"play",foreground));miniToggle.setContentDescription(player.isPlaying()?"Pause":"Play");miniToggle.setEnabled(!player.isLoading());long duration=player.duration();miniProgress.setProgress(duration>0?(int)Math.min(1000,player.position()*1000/duration):0);
    }
    private void playDiscovery(DiscoveryItem item,List<DiscoveryItem> queue){PlaybackController.get(this).play(item,queue);openNowPlaying();}
    private void openNowPlaying(){if(PlaybackController.get(this).current()!=null)startActivity(new Intent(this,NowPlayingActivity.class));}
    private void fileActions(View anchor,File file,JobStore.Job job){
        PopupMenu menu=new PopupMenu(this,anchor);String[] actions={"Open in Music Studio","Share","Save a copy…","Delete local file"};for(int i=0;i<actions.length;i++)menu.getMenu().add(0,i,i,actions[i]);
        menu.setOnMenuItemClickListener(item->{switch(item.getItemId()){
            case 0:DownloadCoordinator.openStudio(this,job.id);break;
            case 1:share(file);break;
            case 2:export(file,job.title);break;
            case 3:new AlertDialog.Builder(this).setTitle("Delete this app file?").setMessage("Exported copies are kept. This removes the file stored inside Blaze.").setNegativeButton("Keep",null).setPositiveButton("Delete",(d,w)->{try{store.deleteCompleted(job.id,DownloadService.folder(this));rendered="";renderJobs();}catch(IOException error){message("Could not delete this file");}}).show();break;
            default:return false;
        }return true;});menu.show();
    }
    private Spinner spinner(String[] values,LinearLayout root){Spinner v=new Spinner(this);ArrayAdapter<String> adapter=new ArrayAdapter<String>(this,android.R.layout.simple_spinner_item,values){
        @Override public View getView(int position,View recycled,ViewGroup parent){TextView view=(TextView)super.getView(position,recycled,parent);view.setTextColor(foreground);view.setTextSize(15);view.setPadding(dp(14),dp(8),dp(12),dp(8));return view;}
        @Override public View getDropDownView(int position,View recycled,ViewGroup parent){TextView view=(TextView)super.getDropDownView(position,recycled,parent);view.setTextColor(foreground);view.setTextSize(16);view.setPadding(dp(16),dp(16),dp(16),dp(16));return view;}
    };adapter.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item);v.setAdapter(adapter);ui.styleSpinner(v);root.addView(v,new LinearLayout.LayoutParams(-1,-2));return v;}
    private TextView text(String value,int size){TextView v=ui.label(value,size,size<=15?muted:foreground);v.setPadding(0,dp(4),0,dp(4));return v;}
    private Button makeButton(String value){return ui.button(value,false);}
    private Button button(String value,LinearLayout parent){Button v=makeButton(value);LinearLayout.LayoutParams layout=new LinearLayout.LayoutParams(-1,-2);layout.topMargin=dp(6);parent.addView(v,layout);return v;}
    private Button smallButton(String value,LinearLayout parent){Button v=makeButton(value);LinearLayout.LayoutParams layout=new LinearLayout.LayoutParams(0,-2,1);layout.setMargins(dp(2),dp(3),dp(2),dp(3));parent.addView(v,layout);return v;}
    private void gap(LinearLayout root,int size){ui.gap(root,size);}
    private int dp(int n){return Math.round(n*getResources().getDisplayMetrics().density);}
    private void message(String value){Toast.makeText(this,value,Toast.LENGTH_LONG).show();}
}
