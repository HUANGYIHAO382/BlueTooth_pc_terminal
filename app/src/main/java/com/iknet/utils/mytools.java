package com.iknet.utils;

import android.content.Context;
import android.content.pm.PackageInfo;
import android.content.pm.PackageManager;
import android.graphics.Bitmap;
import android.os.Handler;
import android.os.Message;
import android.util.Base64;
import android.view.View;

import java.io.ByteArrayOutputStream;
import java.io.IOException;

public class mytools {
    public static void setGeometry(View sv, int left, int top, int width, int height) {
        sv.setLayoutParams(new android.widget.AbsoluteLayout.LayoutParams(
                width, height, left, top));
    }

    public static String printHexString(byte[] b) {
        StringBuffer sb = new StringBuffer();
        for (int i = 0; i < b.length; i++) {
            String hex = Integer.toHexString(b[i] & 0xFF);
            if (hex.length() == 1) {
                hex = '0' + hex;
            }
            sb.append(hex.toUpperCase());
        }
        return sb.toString();
    }

    public static String deal16to10(String str) {
        String rightstr = str.substring(0, 1);
        String leftstr = str.substring(1, 2);
        String r = String.valueOf(Integer.valueOf(get10v(rightstr)) * 16 * 1 + Integer.valueOf(get10v(leftstr)) * 1);
        if (Integer.valueOf(r) < 10) {
            return "0" + r;
        } else {
            return r;
        }
    }

    private static int get10v(String str) {
        str = str.toLowerCase();
        if ("a".equals(str)) {
            return 10;
        } else if ("b".equals(str)) {
            return 11;
        } else if ("c".equals(str)) {
            return 12;
        } else if ("d".equals(str)) {
            return 13;
        } else if ("e".equals(str)) {
            return 14;
        } else if ("f".equals(str)) {
            return 15;
        } else {
            return Integer.valueOf(str);
        }
    }

    public static String stringtohexstr(byte[] tstrby) {
        String rstr = "";

        for (int i = 0; i < tstrby.length; i++) {
            char thex = (char) (tstrby[i] & 0xFF);
            rstr = rstr + Integer.toHexString(thex);
        }
        return rstr;
    }

    public static String bytestostr(byte[] tstrby) {
        int leng = tstrby.length;

        String ptmstr = "";
        for (int i = 0; i < leng; i++) {
            char ptmp = (char) tstrby[i];
            ptmstr = ptmstr + String.valueOf(ptmp);
        }
        return ptmstr;
    }

    public static int bytestoint(byte[] tstrby) {
        try {
            String pbtstr = bytestostr(tstrby);
            char ptms = '\036';
            pbtstr = pbtstr.replace(String.valueOf(ptms), "");
            ptms = ' ';
            pbtstr = pbtstr.replace(String.valueOf(ptms), "");
            return Integer.parseInt(pbtstr);
        } catch (Exception localException) {
        }
        return 0;
    }

    public static byte[] bytecopydata(byte[] tstrby, int starid, int lengs) {
        byte[] scpbyte = new byte[lengs];
        System.arraycopy(tstrby, starid, scpbyte, 0, lengs);
        return scpbyte;
    }

    public static byte[] hextexttobytes(String str) {
        byte[] pretn = new byte[str.length() / 2];
        String calstr = str;
        String rdstr = "";
        int scount = 0;
        while (calstr.length() > 1) {
            rdstr = calstr.substring(0, 2);
            calstr = calstr.substring(2);
            int maid = Integer.parseInt(rdstr, 16);
            pretn[scount] = ((byte) maid);
        }
        return pretn;
    }

    public static void toHandlersendpmt(Handler inhandler, int pmt1, int pmt2) {
        Message message = inhandler.obtainMessage();
        message.arg1 = pmt1;
        message.arg2 = pmt2;
        inhandler.sendMessage(message);
    }

    public static String getVersionName(Context context)
            throws Exception {
        PackageManager packageManager = context.getPackageManager();

        PackageInfo packInfo = packageManager.getPackageInfo(context.getPackageName(), 0);
        return packInfo.versionName;
    }

    public static String bitmapToBase64(Bitmap bitmap) {
        String result = null;
        ByteArrayOutputStream baos = null;
        try {
            if (bitmap != null) {
                baos = new ByteArrayOutputStream();
                bitmap.compress(Bitmap.CompressFormat.JPEG, 100, baos);

                baos.flush();
                baos.close();

                byte[] bitmapBytes = baos.toByteArray();
                result = Base64.encodeToString(bitmapBytes, 0);
            }
        } catch (IOException e) {
            e.printStackTrace();
            try {
                if (baos != null) {
                    baos.flush();
                    baos.close();
                }
            } catch (IOException e1) {
                e1.printStackTrace();
            }
        } finally {
            try {
                if (baos != null) {
                    baos.flush();
                    baos.close();
                }
            } catch (IOException e) {
                e.printStackTrace();
            }
        }
        return result;
    }

}