package com.brooth.blaze;

import android.content.Context;
import android.util.AtomicFile;
import ai.onnxruntime.*;
import org.json.JSONArray;
import org.json.JSONObject;
import java.io.*;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.security.MessageDigest;
import java.util.Collections;
import java.util.Locale;

/** Verified original BTC plus Music X Lab's five pretrained MIT networks. */
final class StudioModels implements AutoCloseable {
    static final int RATE=22050, FRAMES=108, BINS=144, CHUNK=FRAMES*2048;
    static final int[] HEAD_COLUMNS={73,13,4,4,3,3};
    private final OrtEnvironment environment;
    private OrtSession frontend, network;
    private final OrtSession[] advanced=new OrtSession[5];
    final JSONObject manifest, metadata, structured;
    final File directory;
    final String modelHash;
    final String[] labels;
    private final double mean, deviation;
    private final Runnable check;
    static final class Prediction {
        String chord; Double score;
        Prediction(String chord,Double score){this.chord=chord;this.score=score;}
    }
    StudioModels(Context context,String selected)throws Exception{this(context,selected,()->{});}
    StudioModels(Context context,String selected,Runnable check)throws Exception{
        this.check=check;check.run();
        if(!"major_minor".equals(selected)&&!"extended".equals(selected)&&!"powerful".equals(selected))throw new IOException("Choose an installed recognition model.");
        manifest=jsonAsset(context,"manifest.json",65536);
        if(manifest.getInt("schema_version")!=1||manifest.getInt("sample_rate")!=RATE||manifest.getInt("timestep")!=FRAMES)throw new IOException("The recognition model bundle is incompatible.");
        metadata=new JSONObject(manifest.getJSONObject("models").getJSONObject("powerful".equals(selected)?"extended":selected).toString());
        JSONArray names=metadata.getJSONArray("labels");int classes=metadata.getInt("classes");
        if(names.length()!=classes||(classes!=25&&classes!=170))throw new IOException("Invalid recognition vocabulary.");
        labels=new String[classes];for(int i=0;i<classes;i++)labels[i]=names.getString(i);
        mean=metadata.getDouble("mean");deviation=metadata.getDouble("std");
        if(!Double.isFinite(mean)||!Double.isFinite(deviation)||deviation<=0)throw new IOException("Invalid model normalization.");
        structured="powerful".equals(selected)?jsonAsset(context,"structured_manifest.json",1024*1024):null;
        directory=new File(context.getCacheDir(),"studio-verified-models");
        if(!directory.isDirectory()&&!directory.mkdirs())throw new IOException("Could not prepare local models.");
        environment=OrtEnvironment.getEnvironment("BlazeMusicStudio");environment.setTelemetry(false);
        StringBuilder identity=new StringBuilder(metadata.getString("sha256"));
        try(OrtSession.SessionOptions options=new OrtSession.SessionOptions()){
            options.setIntraOpNumThreads(2);options.setInterOpNumThreads(1);options.setExecutionMode(OrtSession.SessionOptions.ExecutionMode.SEQUENTIAL);
            frontend=environment.createSession(verifiedAsset(context,manifest.getJSONObject("frontend"),directory,check).getAbsolutePath(),options);
            check.run();network=environment.createSession(verifiedAsset(context,metadata,directory,check).getAbsolutePath(),options);
            if(structured!=null){
                if(structured.getInt("schema_version")!=1||structured.getInt("feature_size")!=252||structured.getInt("sample_rate")!=RATE||structured.getInt("hop_length")!=512||structured.getJSONArray("models").length()!=5)throw new IOException("Invalid advanced recognition bundle.");
                verifiedAsset(context,structured.getJSONObject("frontend"),directory,check);
                identity.append(structured.getJSONObject("frontend").getString("sha256"));
                writeJson(new File(directory,"structured_manifest.json"),structured);
                for(int i=0;i<5;i++){check.run();JSONObject asset=structured.getJSONArray("models").getJSONObject(i);advanced[i]=environment.createSession(verifiedAsset(context,asset,directory,check).getAbsolutePath(),options);identity.append(asset.getString("sha256"));}
                metadata.put("name","Blaze Advanced Ensemble").put("version","structured-1");
            }
            modelHash=structured==null?metadata.getString("sha256"):hash(identity.toString().getBytes(java.nio.charset.StandardCharsets.UTF_8));
        }catch(Exception error){close();throw error;}
    }
    float[][] probabilities(float[] observed)throws Exception{
        check.run();if(observed.length<128)throw new IOException("The recording is too short for chord recognition.");
        float[] pcm=observed;
        if(pcm.length<4410){pcm=java.util.Arrays.copyOf(pcm,4410);java.util.Arrays.fill(pcm,observed.length,pcm.length,observed[observed.length-1]);}
        double[][] values;
        try(OnnxTensor input=OnnxTensor.createTensor(environment,new float[][]{pcm});OrtSession.Result response=frontend.run(Collections.singletonMap("pcm",input))){values=((double[][][])response.get(0).getValue())[0];}
        int valid=Math.min(FRAMES,Math.min(values.length,(observed.length+2047)/2048));if(valid==0)throw new IOException("No spectral features were decoded.");
        float[][][] features=new float[1][FRAMES][BINS];
        for(int i=0;i<FRAMES;i++){double[] row=values[Math.min(i,valid-1)];if(row.length!=BINS)throw new IOException("Invalid spectral feature shape.");for(int j=0;j<BINS;j++)features[0][i][j]=(float)((row[j]-mean)/deviation);}
        check.run();float[][] logits;
        try(OnnxTensor input=OnnxTensor.createTensor(environment,features);OrtSession.Result response=network.run(Collections.singletonMap("features",input))){logits=((float[][][])response.get(0).getValue())[0];}
        if(logits.length!=FRAMES)throw new IOException("Invalid model output shape.");
        float[][] probabilities=new float[valid][labels.length];
        for(int i=0;i<valid;i++)softmax(logits[i],probabilities[i],labels.length);
        return probabilities;
    }
    Prediction[] predict(float[] pcm)throws Exception{
        float[][] probs=probabilities(pcm);Prediction[] result=new Prediction[probs.length];
        for(int i=0;i<probs.length;i++){float[] row=probs[i];int top=0;for(int c=1;c<row.length;c++)if(row[c]>row[top])top=c;double second=0;for(int c=0;c<row.length;c++)if(c!=top)second=Math.max(second,row[c]);String chord=labels[top];if(!"N".equals(chord)&&(row[top]<.35||row[top]-second<.04))chord="X";result[i]=new Prediction(chord,(double)row[top]);}return result;
    }
    /** One context: Java ORT -> mean softmax heads -> bounded binary bridge. */
    void advancedContext(float[][] features,File output)throws Exception{
        if(structured==null)throw new IOException("Advanced model is not installed.");int count=features.length;
        float[][][] average=new float[6][][];for(int k=0;k<6;k++)average[k]=new float[count][HEAD_COLUMNS[k]];
        for(OrtSession net:advanced){
            check.run();
            try(OnnxTensor input=OnnxTensor.createTensor(environment,new float[][][]{features});OrtSession.Result response=net.run(Collections.singletonMap("features",input))){
                if(response.size()!=6)throw new IOException("Invalid advanced output heads.");
                for(int k=0;k<6;k++){float[][] raw=(float[][])response.get(k).getValue();if(raw.length!=count)throw new IOException("Invalid advanced output length.");float[] probability=new float[HEAD_COLUMNS[k]];for(int t=0;t<count;t++){softmax(raw[t],probability,HEAD_COLUMNS[k]);for(int c=0;c<probability.length;c++)average[k][t][c]+=probability[c]/5f;}}
            }
        }
        try(OutputStream stream=new BufferedOutputStream(new FileOutputStream(output),65536)){ByteBuffer bytes=ByteBuffer.allocate(16384).order(ByteOrder.LITTLE_ENDIAN);for(float[][] head:average)for(float[] row:head)for(float value:row){if(bytes.remaining()<4){stream.write(bytes.array(),0,bytes.position());bytes.clear();}bytes.putFloat(value);}stream.write(bytes.array(),0,bytes.position());}
        check.run();
    }
    private static void softmax(float[] row,float[] result,int columns)throws IOException{
        if(row.length!=columns)throw new IOException("Invalid model vocabulary output.");float highest=-Float.MAX_VALUE;for(float v:row){if(!Float.isFinite(v))throw new IOException("The model returned invalid scores.");highest=Math.max(highest,v);}double sum=0;for(float v:row)sum+=Math.exp(v-highest);for(int c=0;c<row.length;c++)result[c]=(float)(Math.exp(row[c]-highest)/sum);
    }
    static JSONObject jsonAsset(Context context,String name,int maximum)throws Exception{try(InputStream in=context.getAssets().open("musicstudio_models/"+name)){return new JSONObject(new String(read(in,maximum),java.nio.charset.StandardCharsets.UTF_8));}}
    /** Bounded copy of exact self-contained ONNX/NPZ assets; checksum every load. */
    static synchronized File verifiedAsset(Context context,JSONObject metadata,File directory,Runnable check)throws Exception{
        String name=metadata.getString("file"),expected=metadata.getString("sha256");
        if(!name.matches("[a-zA-Z0-9_.-]+\\.(onnx|npz)")||!expected.matches("[a-f0-9]{64}"))throw new IOException("Invalid model asset name.");
        if(!directory.isDirectory()&&!directory.mkdirs())throw new IOException("Could not prepare local models.");
        File destination=new File(directory,name);
        if(destination.isFile()&&destination.length()<=700L*1024*1024){MessageDigest digest=MessageDigest.getInstance("SHA-256");try(InputStream stream=new FileInputStream(destination)){byte[] bytes=new byte[65536];int n;while((n=stream.read(bytes))!=-1){check.run();digest.update(bytes,0,n);}}if(hex(digest.digest()).equals(expected))return destination;}
        AtomicFile target=new AtomicFile(destination);FileOutputStream out=null;
        try(InputStream stream=context.getAssets().open("musicstudio_models/"+name)){
            out=target.startWrite();MessageDigest digest=MessageDigest.getInstance("SHA-256");byte[] bytes=new byte[65536];long total=0;int n;while((n=stream.read(bytes))!=-1){check.run();total+=n;if(total>700L*1024*1024)throw new IOException("Recognition model is too large.");digest.update(bytes,0,n);out.write(bytes,0,n);}
            if(!hex(digest.digest()).equals(expected))throw new IOException("Recognition model verification failed. Reinstall the complete Blaze APK.");target.finishWrite(out);
        }catch(Exception error){if(out!=null)target.failWrite(out);throw error;}return destination;
    }
    private static void writeJson(File path,JSONObject data)throws IOException{AtomicFile target=new AtomicFile(path);FileOutputStream out=target.startWrite();try{out.write(data.toString().getBytes(java.nio.charset.StandardCharsets.UTF_8));target.finishWrite(out);}catch(IOException e){target.failWrite(out);throw e;}}
    static byte[] read(InputStream input,int limit)throws IOException{ByteArrayOutputStream output=new ByteArrayOutputStream();byte[] buffer=new byte[65536];int n;while((n=input.read(buffer))!=-1){if(output.size()+(long)n>limit)throw new IOException("The model asset is too large.");output.write(buffer,0,n);}return output.toByteArray();}
    static String hash(byte[] value)throws Exception{return hex(MessageDigest.getInstance("SHA-256").digest(value));}
    private static String hex(byte[] bytes){StringBuilder result=new StringBuilder();for(byte b:bytes)result.append(String.format(Locale.ROOT,"%02x",b&255));return result.toString();}
    @Override public void close()throws OrtException{OrtException first=null;if(frontend!=null){try{frontend.close();}catch(OrtException e){first=e;}frontend=null;}if(network!=null){try{network.close();}catch(OrtException e){first=e;}network=null;}for(int i=0;i<advanced.length;i++)if(advanced[i]!=null){try{advanced[i].close();}catch(OrtException e){first=e;}advanced[i]=null;}if(first!=null)throw first;}
}
