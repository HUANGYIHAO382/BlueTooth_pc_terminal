package com.iknet.iknetbluetoothlibrary;


import java.io.Serializable;

public class MeasurementResult implements Serializable {

	/**
	 * 测量结果得到的数据
	 * 
	 * {"appStatus":{"errorCode":"00000","success":true,"msg":"查询成功"},
	 * "appTestData": [{"personId":65,"createTime":1413811493929,
	 * "updateTime":1413811493929,"checkDiastole":null,"checkShrink":null,
	 * "checkHeartRate"
	 * :null,"equipType":null,"testDataId":129,"checkDate":1413811493929,
	 * "equipCode":null,"companyCode":null,"equipPid":null},
	 * 
	 * 
	 */

	private static final long serialVersionUID = 1L;

	private String personId;
	private int _id;// 病例号

	public int get_id() {
		return _id;
	}

	public void set_id(int _id) {
		this._id = _id;
	}

	private int checkShrink;// 收缩压
	private int checkDiastole;// 舒张压
	private int checkHeartRate;// 心率
	private int pulse;// 脉搏差

	private long createTime;
	private String updateTime;
	private String testDataId;
	private String equipType;// 设备类型
	private String equipPid;// 设备id
	private String checkResult;
	private boolean isUpload;// 是否上传
	private String uploadDate;// 上传的日期
	private String medicalRecordRemark;// 医生嘱咐
	private String checkAutoFrom;// 测量数据来源 I:IOS;A:Android
	private String checkAutoFlag;// 自动测量标识 Y:自动测量 N:手动输入测量自动测量标识
	private String bluetoothName;  //血压计设备名称

	public String getPersonId() {
		return personId;
	}

	public void setPersonId(String personId) {
		this.personId = personId;
	}

	public int getCheckDiastole() {
		return checkDiastole;
	}

	public void setCheckDiastole(int checkDiastole) {
		this.checkDiastole = checkDiastole;
	}

	public int getCheckShrink() {
		return checkShrink;
	}

	public void setCheckShrink(int checkShrink) {
		this.checkShrink = checkShrink;
	}

	public int getCheckHeartRate() {
		return checkHeartRate;
	}

	public void setCheckHeartRate(int checkHeartRate) {
		this.checkHeartRate = checkHeartRate;
	}

	public int getPulse() {
		return pulse;
	}

	public void setPulse(int pulse) {
		this.pulse = pulse;
	}

	public long getCreateTime() {
		return createTime;
	}

	public void setCreateTime(long createTime) {
		this.createTime = createTime;
	}

	public String getUpdateTime() {
		return updateTime;
	}

	public void setUpdateTime(String updateTime) {
		this.updateTime = updateTime;
	}

	public String getTestDataId() {
		return testDataId;
	}

	public void setTestDataId(String testDataId) {
		this.testDataId = testDataId;
	}

	public String getEquipType() {
		return equipType;
	}

	public void setEquipType(String equipType) {
		this.equipType = equipType;
	}

	public String getEquipPid() {
		return equipPid;
	}

	public void setEquipPid(String equipPid) {
		this.equipPid = equipPid;
	}

	public String getCheckResult() {
		return checkResult;
	}

	public void setCheckResult(String checkResult) {
		this.checkResult = checkResult;
	}

	public boolean isUpload() {
		return isUpload;
	}

	public void setUpload(boolean isUpload) {
		this.isUpload = isUpload;
	}

	public String getUploadDate() {
		return uploadDate;
	}

	public void setUploadDate(String uploadDate) {
		this.uploadDate = uploadDate;
	}

	public String getMedicalRecordRemark() {
		return medicalRecordRemark;
	}

	public void setMedicalRecordRemark(String medicalRecordRemark) {
		this.medicalRecordRemark = medicalRecordRemark;
	}

	public String getCheckAutoFrom() {
		return checkAutoFrom;
	}

	public void setCheckAutoFrom(String checkAutoFrom) {
		this.checkAutoFrom = checkAutoFrom;
	}

	public String getCheckAutoFlag() {
		return checkAutoFlag;
	}

	public void setCheckAutoFlag(String checkAutoFlag) {
		this.checkAutoFlag = checkAutoFlag;
	}

	@Override
	public String toString() {
		return "MeasurementResult [personId=" + personId + ", _id=" + _id
				+ ", checkShrink=" + checkShrink + ", checkDiastole="
				+ checkDiastole + ", checkHeartRate=" + checkHeartRate
				+ ", pulse=" + pulse + ", createTime=" + createTime
				+ ", updateTime=" + updateTime + ", testDataId=" + testDataId
				+ ", equipType=" + equipType + ", equipPid=" + equipPid
				+ ", checkResult=" + checkResult + ", isUpload=" + isUpload
				+ ", uploadDate=" + uploadDate + ", medicalRecordRemark="
				+ medicalRecordRemark + ", checkAutoFrom=" + checkAutoFrom
				+ ", checkAutoFlag=" + checkAutoFlag + "]";
	}

	public String getBluetoothName() {
		return bluetoothName;
	}

	public void setBluetoothName(String bluetoothName) {
		this.bluetoothName = bluetoothName;
	}

}
