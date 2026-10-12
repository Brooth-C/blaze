package com.brooth.blaze;
/** Complete BTC-170 vocabulary, alongside retained legacy triad IDs. */
final class StudioChord {
    static final String[] QUALITY={"min","maj","dim","aug","min6","maj6","min7","minmaj7","maj7","7","dim7","hdim7","sus2","sus4","9","maj9","min9","11","13"};
    static final String[] SUFFIX={"m","","dim","aug","m6","6","m7","m(maj7)","maj7","7","dim7","m7b5","sus2","sus4","9","maj9","m9","11","13"};
    static final int[][] NOTES={{0,3,7},{0,4,7},{0,3,6},{0,4,8},{0,3,7,9},{0,4,7,9},{0,3,7,10},{0,3,7,11},{0,4,7,11},{0,4,7,10},{0,3,6,9},{0,3,6,10},{0,2,7},{0,5,7},{0,4,7,10,2},{0,4,7,11,2},{0,3,7,10,2},{0,4,7,10,2,5},{0,4,7,10,2,5,9}};
    static int root(int code){return code<24?Math.floorMod(code,12):code<192?(code-24)/14:(code-192)/5;}
    static int quality(int code){return code<24?(code<12?1:0):code<192?(code-24)%14:14+(code-192)%5;}
    static int parse(String text){if("N".equals(text))return -1;if("X".equals(text))return -2;String[] p=text.split(":");if(p.length!=2)return -2;for(int r=0;r<12;r++)if(ChordEngine.NOTES[r].equals(p[0]))for(int q=0;q<19;q++)if(QUALITY[q].equals(p[1]))return q<14?24+r*14+q:192+r*5+q-14;return -2;}
    static String label(int code,int shift){if(code==-1)return "No chord";if(code<0)return "Uncertain";return ChordEngine.NOTES[Math.floorMod(root(code)+shift,12)]+SUFFIX[quality(code)];}
    static String canonical(int code,int shift){if(code==-1)return "N";if(code<0)return "X";return ChordEngine.NOTES[Math.floorMod(root(code)+shift,12)]+":"+QUALITY[quality(code)];}
    static int transpose(int code,int shift){if(code<0)return code;int r=Math.floorMod(root(code)+shift,12),q=quality(code);return q<14?24+r*14+q:192+r*5+q-14;}
    static boolean contains(int code,int note){if(code<0)return false;int interval=Math.floorMod(note-root(code),12);for(int n:NOTES[quality(code)])if(n==interval)return true;return false;}
    private static final java.util.Map<Integer,int[]> VOICINGS=new java.util.HashMap<>();
    static synchronized int[] voicing(int code){if(VOICINGS.containsKey(code))return VOICINGS.get(code);int mask=0;for(int n:NOTES[quality(code)])mask|=1<<Math.floorMod(root(code)+n,12);if(Integer.bitCount(mask)>6){VOICINGS.put(code,null);return null;}int[] best=null;int cost=Integer.MAX_VALUE;for(int first=1;first<=12;first++){int[] chosen=new int[6];Search search=new Search(mask,root(code),first);search.walk(0,0,0,chosen);if(search.best!=null&&search.cost<cost){best=search.best;cost=search.cost;}}VOICINGS.put(code,best);return best;}
    private static final class Search{final int mask,root,first;int[] best;int cost=Integer.MAX_VALUE;final int[] tuning={4,9,2,7,11,4};Search(int m,int r,int f){mask=m;root=r;first=f;}
        void walk(int string,int used,int score,int[] shape){if(score>=cost)return;if(string==6){if((used&mask)==mask){int voiced=0,bass=-1;for(int i=0;i<6;i++)if(shape[i]>=0){voiced++;if(bass<0)bass=(tuning[i]+shape[i])%12;}if(voiced>=3){int total=score+(bass==root?0:4);if(total<cost){cost=total;best=shape.clone();}}}return;}
            shape[string]=-1;walk(string+1,used,score+3,shape);for(int fret=0;fret<=first+3;fret++){if(fret>0&&fret<first)continue;int pitch=(tuning[string]+fret)%12;if((mask&(1<<pitch))==0)continue;shape[string]=fret;walk(string+1,used|(1<<pitch),score+(fret==0?0:1)+first/4,shape);}
        }
    }
}

