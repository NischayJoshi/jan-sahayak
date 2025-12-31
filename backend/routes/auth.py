from fastapi import APIRouter, HTTPException,Depends
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from controllers.auth import hash_password,verify_password,create_access_token
from config.db import db

router = APIRouter(tags=["Authentication"])

class UserCreate(BaseModel):
    username : str | None = None
    firstName : str | None = None
    lastName : str | None = None 
    email : str | None = None 
    password : str
    phone : Optional[str] | None = None
    date_of_birth : str | None = None
    gender : str | None = None 
    role: str | None = None

class LoginBase(BaseModel):
    username : Optional[str] | None = None
    email : Optional[str] | None = None
    password : str | None = None 

@router.post("/signup")
async def signUp(user: UserCreate):
    print(len(user.password))
    try:
        collection = db["users"]
        print(len(user.password))
        existing = await collection.find_one({"email": user.email})
        if(existing):
            raise HTTPException(status_code=400,detail="User email already registered")
        
        user_data = user.dict()
        print(len(user.password))
        user_data["password"] = hash_password(user.password)
        print(user_data["password"])
        user_data["created_at"] = datetime.utcnow()

        res = await collection.insert_one(user_data)

        if(not res.acknowledged):
            return HTTPException(status_code=500,detail="Failed to Create Account")
        
        token = create_access_token({"id" : str(res.inserted_id), "username" : user.username, "role" : user.role})
        return {
            "success" : True,
            "message": f"User Created Successfully {user.username}",
            "access_token" : token
        }
    except HTTPException as HE :
        raise HE
    except Exception as e :
        raise HTTPException(status_code=500,detail=str(e))
    
@router.post("/login")
async def login(user: LoginBase):
    try:
        collection = db["users"]
        query = {}
        if user.username:
            query["username"] = user.username
        elif user.email:
            query["email"] = user.email
        else:
            raise HTTPException(status_code=400, detail="Username or email required")

        existing = await collection.find_one(query)
        if(not existing or not verify_password(user.password,existing["password"])):
            raise HTTPException(status_code=401,detail="Invalid Credentials!")
        
        token = create_access_token({"id" : str(existing["_id"]),"username" : existing["username"], "role": existing["role"]})
        
        return {
            "success" : True,
            "message" : "Login Successfull",
            "access_token" : token
        }
    
    except HTTPException as HE:
        raise HE
    except Exception as e:
        raise HTTPException(status_code=500,detail=str(e))
    