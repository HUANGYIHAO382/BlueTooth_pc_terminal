package com.iknet.iknetbluetoothlibrary.model;

/**
 * 从血压计返回的数据解析后的对象
 * @author Administrator
 *
 */
public class ResultFromTurg {
	
	private int flag = 0;// 类型标记
	private int sflag = 0;// 类型子码
	private byte[] dataBuff = null;
	
	public int getFlag() {
		return flag;
	}
	public void setFlag(int flag) {
		this.flag = flag;
	}
	public int getSflag() {
		return sflag;
	}
	public void setSflag(int sflag) {
		this.sflag = sflag;
	}
	public byte[] getDataBuff() {
		return dataBuff;
	}
	public void setDataBuff(byte[] dataBuff) {
		this.dataBuff = dataBuff;
	}

}
