@call .venv\scripts\activate
@if "%1"=="" goto :EOF
%*
deactivate
