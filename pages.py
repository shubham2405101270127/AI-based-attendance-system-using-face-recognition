"""Serves HTML pages - Feature 2 adds /faculty route."""
from fastapi import APIRouter
from fastapi.responses import FileResponse

router = APIRouter()

@router.get("/")
async def index():    return FileResponse("templates/index.html")

@router.get("/dashboard")
async def dashboard(): return FileResponse("templates/dashboard.html")

@router.get("/register")
async def register():  return FileResponse("templates/register.html")

@router.get("/session")
async def session():   return FileResponse("templates/session.html")

@router.get("/faculty")
async def faculty():   return FileResponse("templates/faculty.html")
