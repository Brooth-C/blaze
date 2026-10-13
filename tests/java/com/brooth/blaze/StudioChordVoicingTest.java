package com.brooth.blaze;
public class StudioChordVoicingTest {
 public static void main(String[] args) {
  int[] tuning={4,9,2,7,11,4};
  for(String label:new String[]{"C:maj/E","A:min/C","C:maj7/B","D:min7/A"}) {
   int code=StudioChord.parse(label);int[] shape=StudioChord.voicing(code);
   if(shape==null)throw new AssertionError("Missing playable fixture "+label);
   int bass=-1;for(int i=0;i<6;i++)if(shape[i]>=0){bass=(tuning[i]+shape[i])%12;break;}
   if(bass!=StudioChord.bass(code))throw new AssertionError("Wrong slash bass "+label);
  }
  System.out.println("Slash chord guitar voicings preserve the requested lowest note");
 }
}
