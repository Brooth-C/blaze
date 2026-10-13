package com.brooth.blaze;
import android.content.Context;
import android.graphics.*;
import android.view.*;

/** Actual decoded amplitude peaks with the player's position; no illustrative data. */
final class StudioWaveformView extends View {
    interface Seek {void to(long millis);}
    Seek seek;private float[] peaks=new float[0];private long duration,position;private final Paint paint=new Paint(Paint.ANTI_ALIAS_FLAG);
    StudioWaveformView(Context context){super(context);setFocusable(true);setContentDescription("Audio waveform. Tap to seek.");}
    void show(float[] values,long length){peaks=values;duration=length;invalidate();}
    void position(long time){position=time;invalidate();}
    @Override protected void onDraw(Canvas canvas){super.onDraw(canvas);if(peaks.length==0)return;int bars=Math.min(peaks.length,Math.max(1,getWidth()/8));float maximum=.02f;for(float p:peaks)maximum=Math.max(maximum,p);float ratio=duration>0?Math.max(0,Math.min(1,(float)position/duration)):0;
        for(int i=0;i<bars;i++){float peak=0;for(int j=i*peaks.length/bars;j<Math.max(i*peaks.length/bars+1,(i+1)*peaks.length/bars);j++)peak=Math.max(peak,peaks[j]);float x=(i+.5f)*getWidth()/bars,height=Math.max(3,peak/maximum*(getHeight()-12));paint.setColor(x/getWidth()<=ratio?0xffff8c42:0xff657388);canvas.drawRoundRect(x-2,(getHeight()-height)/2,x+2,(getHeight()+height)/2,2,2,paint);}
        paint.setColor(0xffedf0f6);paint.setStrokeWidth(2);canvas.drawLine(ratio*getWidth(),0,ratio*getWidth(),getHeight(),paint);
    }
    @Override public boolean onTouchEvent(MotionEvent event){if(event.getAction()==MotionEvent.ACTION_UP&&duration>0&&seek!=null){performClick();seek.to((long)(Math.max(0,Math.min(1,event.getX()/Math.max(1,getWidth())))*duration));return true;}return event.getAction()==MotionEvent.ACTION_DOWN;}
    @Override public boolean performClick(){super.performClick();return true;}
    @Override public boolean onKeyDown(int code,KeyEvent event){
        if(seek==null||duration<=0)return super.onKeyDown(code,event);
        if(code==KeyEvent.KEYCODE_DPAD_LEFT){seek.to(Math.max(0,position-5000));return true;}
        if(code==KeyEvent.KEYCODE_DPAD_RIGHT){seek.to(Math.min(duration,position+5000));return true;}
        return super.onKeyDown(code,event);
    }
    @Override public void onInitializeAccessibilityNodeInfo(android.view.accessibility.AccessibilityNodeInfo info){
        super.onInitializeAccessibilityNodeInfo(info);info.setClassName("android.widget.SeekBar");
        info.setRangeInfo(android.view.accessibility.AccessibilityNodeInfo.RangeInfo.obtain(android.view.accessibility.AccessibilityNodeInfo.RangeInfo.RANGE_TYPE_FLOAT,0,100,duration>0?Math.max(0,Math.min(100,100f*position/duration)):0));
        if(duration>0)info.addAction(android.view.accessibility.AccessibilityNodeInfo.AccessibilityAction.ACTION_SET_PROGRESS);
    }
    @Override public boolean performAccessibilityAction(int action,android.os.Bundle args){
        if(action==android.view.accessibility.AccessibilityNodeInfo.AccessibilityAction.ACTION_SET_PROGRESS.getId()&&args!=null&&duration>0&&seek!=null){float value=args.getFloat(android.view.accessibility.AccessibilityNodeInfo.ACTION_ARGUMENT_PROGRESS_VALUE);seek.to((long)(duration*Math.max(0,Math.min(100,value))/100));return true;}
        return super.performAccessibilityAction(action,args);
    }
}
