package com.brooth.blaze;

import android.content.Context;
import ai.onnxruntime.*;
import org.json.JSONArray;
import org.json.JSONObject;
import java.io.*;
import java.security.MessageDigest;
import java.util.Collections;
import java.util.Locale;

/** Frozen pretrained BTC checkpoints and faithful portable CQT, with no training or downloads. */
final class StudioModels implements AutoCloseable {
    static final int RATE=22050, CHUNK=220500, FRAMES=108, BINS=144;
    private final OrtEnvironment environment;
    private OrtSession frontend, network;
    final JSONObject manifest, metadata;
    private final String[] labels;
    private final double mean, deviation;
    static final class Prediction {
        String chord;
        Double score;
        Prediction(String chord, Double score){this.chord=chord;this.score=score;}
    }
    StudioModels(Context context,String selected)throws Exception {
        if(!"major_minor".equals(selected)&&!"extended".equals(selected))throw new IOException("Choose an installed recognition model.");
        try(InputStream in=context.getAssets().open("musicstudio_models/manifest.json")){
            manifest=new JSONObject(new String(read(in,65536),java.nio.charset.StandardCharsets.UTF_8));
        }catch(IOException error){throw new IOException("Recognition models are missing. Install the complete Music Studio build.",error);}
        if(manifest.getInt("schema_version")!=1||manifest.getInt("sample_rate")!=RATE||manifest.getInt("timestep")!=FRAMES)throw new IOException("The recognition model bundle is incompatible.");
        metadata=manifest.getJSONObject("models").getJSONObject(selected);
        JSONArray names=metadata.getJSONArray("labels");int classes=metadata.getInt("classes");
        if(names.length()!=classes||(classes!=25&&classes!=170))throw new IOException("Invalid recognition vocabulary.");
        labels=new String[classes];for(int i=0;i<classes;i++)labels[i]=names.getString(i);
        mean=metadata.getDouble("mean");deviation=metadata.getDouble("std");
        if(!Double.isFinite(mean)||!Double.isFinite(deviation)||deviation<=0)throw new IOException("Invalid model normalization.");
        environment=OrtEnvironment.getEnvironment("BlazeMusicStudio");environment.setTelemetry(false);
        try(OrtSession.SessionOptions options=new OrtSession.SessionOptions()){
            options.setIntraOpNumThreads(2);options.setInterOpNumThreads(1);
            options.setExecutionMode(OrtSession.SessionOptions.ExecutionMode.SEQUENTIAL);
            frontend=environment.createSession(asset(context,manifest.getJSONObject("frontend")),options);
            network=environment.createSession(asset(context,metadata),options);
        }catch(Exception error){close();throw error;}
    }
    Prediction[] predict(float[] pcm)throws Exception {
        if(pcm.length<128)throw new IOException("The recording is too short for chord recognition.");
        double[][] values;
        try(OnnxTensor input=OnnxTensor.createTensor(environment,new float[][]{pcm});
            OrtSession.Result response=frontend.run(Collections.singletonMap("pcm",input))){
            values=((double[][][])response.get(0).getValue())[0];
        }
        int valid=Math.min(FRAMES,values.length);if(valid==0)throw new IOException("No spectral features were decoded.");
        float[][][] features=new float[1][FRAMES][BINS];
        for(int i=0;i<FRAMES;i++){
            double[] row=values[Math.min(i,valid-1)];if(row.length!=BINS)throw new IOException("Invalid spectral feature shape.");
            for(int j=0;j<BINS;j++)features[0][i][j]=(float)((row[j]-mean)/deviation);
        }
        float[][] logits;
        try(OnnxTensor input=OnnxTensor.createTensor(environment,features);
            OrtSession.Result response=network.run(Collections.singletonMap("features",input))){
            logits=((float[][][])response.get(0).getValue())[0];
        }
        if(logits.length!=FRAMES)throw new IOException("Invalid model output shape.");
        Prediction[] predictions=new Prediction[valid];
        for(int i=0;i<valid;i++){
            float[] row=logits[i];if(row.length!=labels.length)throw new IOException("Invalid model vocabulary output.");
            int first=0;for(int j=0;j<row.length;j++){if(!Float.isFinite(row[j]))throw new IOException("The recognition model returned invalid scores.");if(row[j]>row[first])first=j;}
            double sum=0,second=0;for(int j=0;j<row.length;j++){double value=Math.exp(row[j]-row[first]);sum+=value;if(j!=first)second=Math.max(second,value);}
            double score=1/sum;String chord=labels[first];
            if(!"N".equals(chord)&&(score<.35||score-second/sum<.04))chord="X";
            float energy=0;int left=Math.max(0,i*2048-4096),right=Math.min(pcm.length,i*2048+4096);
            for(int j=left;j<right;j++)energy=Math.max(energy,Math.abs(pcm[j]));
            predictions[i]=energy<1e-5f?new Prediction("N",0.0):new Prediction(chord,score);
        }
        return predictions;
    }
    private static byte[] asset(Context context,JSONObject metadata)throws Exception {
        String name=metadata.getString("file");if(!name.matches("[a-zA-Z0-9_.-]+\\.onnx"))throw new IOException("Invalid model asset name.");
        byte[] bytes;try(InputStream in=context.getAssets().open("musicstudio_models/"+name)){bytes=read(in,700*1024*1024);}
        if(!hash(bytes).equals(metadata.getString("sha256")))throw new IOException("Recognition model verification failed. Reinstall the complete build.");
        return bytes;
    }
    static byte[] read(InputStream input,int limit)throws IOException {
        ByteArrayOutputStream output=new ByteArrayOutputStream();byte[] buffer=new byte[65536];int n;
        while((n=input.read(buffer))!=-1){if(output.size()+(long)n>limit)throw new IOException("The model asset is too large.");output.write(buffer,0,n);}
        return output.toByteArray();
    }
    static String hash(byte[] value)throws Exception {
        MessageDigest digest=MessageDigest.getInstance("SHA-256");StringBuilder result=new StringBuilder();
        for(byte b:digest.digest(value))result.append(String.format(Locale.ROOT,"%02x",b&255));return result.toString();
    }
    @Override public void close() throws OrtException {if(frontend!=null){frontend.close();frontend=null;}if(network!=null){network.close();network=null;}}
}
