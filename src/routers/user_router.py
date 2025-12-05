from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from src.user_service import UserService, UserStatus

router = APIRouter(tags=["用户中心"])

class SetStatusReq(BaseModel):
    mobile: str = Field(..., example="13800138000")
    new_status: UserStatus = Field(..., description="0-正常 1-冻结 2-注销")
    reason: str = Field("后台调整", max_length=255)

class SetStatusResp(BaseModel):
    success: bool

@router.post("/user/set-status", response_model=SetStatusResp)
def set_status(body: SetStatusReq):
    try:
        ok = UserService.set_status(body.mobile, body.new_status, body.reason)
        return SetStatusResp(success=ok)
    except ValueError as e:
        raise HTTPException(400, detail=str(e))