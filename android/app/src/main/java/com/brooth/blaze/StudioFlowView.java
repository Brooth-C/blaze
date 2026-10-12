package com.brooth.blaze;
import android.content.Context;
import android.graphics.*;
import android.os.Bundle;
import android.text.TextUtils;
import android.view.*;
import androidx.core.view.ViewCompat;
import androidx.core.view.accessibility.AccessibilityNodeInfoCompat;
import androidx.customview.widget.ExploreByTouchHelper;
import java.util.*;

/** Four measures, one continuous progress line each, driven by LibVLC timestamps. */
final class StudioFlowView extends View {
    interface Seek{void to(long time);}
    Seek seek;private StudioTimeline timeline;private StudioTimeline.State state;private int transpose;private float downX,downY;private boolean moved;private final Paint paint=new Paint(Paint.ANTI_ALIAS_FLAG);private final android.text.TextPaint text=new android.text.TextPaint(Paint.ANTI_ALIAS_FLAG);private final Access access;
    StudioFlowView(Context c){super(c);setFocusable(true);setImportantForAccessibility(IMPORTANT_FOR_ACCESSIBILITY_YES);access=new Access(this);ViewCompat.setAccessibilityDelegate(this,access);setContentDescription("Live Chord Flow");}
    void show(StudioTimeline map,int shift){timeline=map;transpose=shift;state=map==null?null:map.state(0);invalidate();access.invalidateRoot();}
    void position(long time){if(timeline==null)return;if(state!=null&&state.time==Math.max(0,Math.min(timeline.duration,time)))return;int oldGroup=state==null?-1:state.group,oldChord=state==null?-1:state.chord;state=timeline.state(time);invalidate();if(oldGroup!=state.group||oldChord!=state.chord)access.invalidateRoot();}
    private int first(){return state==null?0:timeline.barStart+state.group*4;}
    private int count(){return timeline==null?0:Math.min(4,timeline.measures.size()-first());}
    private String name(int i){StudioTimeline.Measure m=timeline.measures.get(i);return ("unknown".equals(m.kind)?"Window ":"Bar ")+(i-timeline.barStart+1);}
    private float dp(float n){return n*getResources().getDisplayMetrics().density*Math.max(1,getResources().getConfiguration().fontScale);}
    @Override protected void onDraw(Canvas c){super.onDraw(c);if(timeline==null||state==null)return;float width=getWidth()/4f,gap=dp(6),top=dp(37),bottom=dp(88),line=dp(108);text.setTypeface(Typeface.create(Typeface.DEFAULT,Typeface.NORMAL));text.setTextSize(13*getResources().getDisplayMetrics().scaledDensity);
        for(int k=0;k<count();k++){int i=first()+k;StudioTimeline.Measure m=timeline.measures.get(i);float left=k*width+gap,right=(k+1)*width-gap;boolean active=i==state.measure&&!state.ended;paint.setStyle(Paint.Style.FILL);paint.setColor(active?0xff2c211d:0xff1d2331);c.drawRoundRect(left,dp(5),right,getHeight()-dp(5),dp(10),dp(10),paint);paint.setStyle(Paint.Style.STROKE);paint.setStrokeWidth(dp(1));paint.setColor(active?0xffff8c42:0xff303a4c);c.drawRoundRect(left,dp(5),right,getHeight()-dp(5),dp(10),dp(10),paint);paint.setStyle(Paint.Style.FILL);text.setColor(active?0xffff8c42:0xffa8b1c5);c.drawText(name(i)+(active?" · NOW":""),left+gap,dp(27),text);
            for(StudioTimeline.Region r:m.regions){float a=left+gap+(r.start-m.start)/(float)(m.end-m.start)*(right-left-2*gap),b=left+gap+(r.end-m.start)/(float)(m.end-m.start)*(right-left-2*gap);text.setColor(r.index==state.chord&&!state.ended?0xffff8c42:state.time>=m.end?0xffa8b1c5:0xffedf0f6);String label=StudioChord.label(r.chord,transpose);CharSequence fit=TextUtils.ellipsize(label,text,Math.max(0,b-a-dp(6)),TextUtils.TruncateAt.END);c.drawText(fit.toString(),a+dp(3),(top+bottom)/2,text);paint.setColor(0xff303a4c);paint.setStrokeWidth(dp(1));if(r.end<m.end)c.drawLine(b,top,b,bottom,paint);}
            double progress=Math.max(0,Math.min(1,(double)(state.time-m.start)/(m.end-m.start)));paint.setColor(0xff657388);paint.setStrokeWidth(dp(3));c.drawLine(left+gap,line,right-gap,line,paint);paint.setColor(0xffff8c42);float x=(float)(left+gap+(right-left-2*gap)*progress);c.drawLine(left+gap,line,x,line,paint);if(active){paint.setColor(0xffedf0f6);paint.setStrokeWidth(dp(2));c.drawLine(x,top,x,line+dp(4),paint);}
        }
    }
    @Override public boolean onTouchEvent(MotionEvent e){if(timeline==null)return false;if(e.getAction()==MotionEvent.ACTION_DOWN){downX=e.getX();downY=e.getY();moved=false;return true;}if(e.getAction()==MotionEvent.ACTION_MOVE){if(Math.hypot(e.getX()-downX,e.getY()-downY)>ViewConfiguration.get(getContext()).getScaledTouchSlop())moved=true;return true;}if(e.getAction()==MotionEvent.ACTION_CANCEL){moved=true;return true;}if(e.getAction()==MotionEvent.ACTION_UP){if(moved)return true;performClick();int k=Math.max(0,Math.min(3,(int)(e.getX()/(getWidth()/4f))));if(k>=count())return true;StudioTimeline.Measure m=timeline.measures.get(first()+k);float local=(e.getX()-k*getWidth()/4f-2*dp(6))/(getWidth()/4f-4*dp(6));long t=m.start+(long)(Math.max(0,Math.min(1,local))*(m.end-m.start));if(e.getY()<dp(32))t=m.start;else if(e.getY()<dp(90))for(StudioTimeline.Region r:m.regions)if(t>=r.start&&t<r.end){t=r.start;break;}if(seek!=null)seek.to(t);return true;}return false;}
    @Override public boolean performClick(){super.performClick();return true;}
    @Override public boolean onKeyDown(int code,KeyEvent event){if(state==null||seek==null)return super.onKeyDown(code,event);long t=state.time;if(code==KeyEvent.KEYCODE_DPAD_LEFT)t-=250;else if(code==KeyEvent.KEYCODE_DPAD_RIGHT)t+=250;else if(code==KeyEvent.KEYCODE_MOVE_HOME)t=timeline.measures.get(state.measure).start;else if(code==KeyEvent.KEYCODE_MOVE_END)t=timeline.measures.get(state.measure).end;else return super.onKeyDown(code,event);seek.to(Math.max(0,Math.min(timeline.duration,t)));return true;}
    @Override public boolean dispatchHoverEvent(MotionEvent event){return access.dispatchHoverEvent(event)||super.dispatchHoverEvent(event);}
    private final class Access extends ExploreByTouchHelper{
        Access(View v){super(v);}
        @Override protected int getVirtualViewAt(float x,float y){int k=(int)(x/(getWidth()/4f));return k>=0&&k<count()?k:INVALID_ID;}
        @Override protected void getVisibleVirtualViews(List<Integer> ids){for(int i=0;i<count();i++)ids.add(i);}
        @Override protected void onPopulateNodeForVirtualView(int id,AccessibilityNodeInfoCompat node){if(id<0||id>=count()){node.setContentDescription("End of recording");node.setBoundsInParent(new Rect(0,0,1,1));node.setEnabled(false);return;}StudioTimeline.Measure m=timeline.measures.get(first()+id);StringBuilder label=new StringBuilder(name(first()+id));for(StudioTimeline.Region r:m.regions)label.append(", ").append(StudioChord.label(r.chord,transpose));node.setContentDescription(label);node.setClassName("android.widget.SeekBar");node.setBoundsInParent(new Rect(Math.round(id*getWidth()/4f),0,Math.round((id+1)*getWidth()/4f),getHeight()));node.addAction(AccessibilityNodeInfoCompat.ACTION_CLICK);node.addAction(AccessibilityNodeInfoCompat.AccessibilityActionCompat.ACTION_SET_PROGRESS);float progress=state==null?0:(float)Math.max(0,Math.min(100,100.0*(state.time-m.start)/(m.end-m.start)));node.setRangeInfo(AccessibilityNodeInfoCompat.RangeInfoCompat.obtain(AccessibilityNodeInfoCompat.RangeInfoCompat.RANGE_TYPE_FLOAT,0,100,progress));}
        @Override protected boolean onPerformActionForVirtualView(int id,int action,Bundle args){if(seek==null||id<0||id>=count())return false;StudioTimeline.Measure m=timeline.measures.get(first()+id);if(action==AccessibilityNodeInfoCompat.ACTION_CLICK){seek.to(m.start);return true;}if(action==AccessibilityNodeInfoCompat.AccessibilityActionCompat.ACTION_SET_PROGRESS.getId()&&args!=null){float percent=args.getFloat(AccessibilityNodeInfoCompat.ACTION_ARGUMENT_PROGRESS_VALUE);seek.to(m.start+(long)(Math.max(0,Math.min(100,percent))/100*(m.end-m.start)));return true;}return false;}
    }
}
