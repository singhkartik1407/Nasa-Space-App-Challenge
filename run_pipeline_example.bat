@echo off
REM Edit the two filenames below to match your downloaded FIRMS CSV files.
python scripts\01_create_structure.py
python scripts\02_convert_and_audit.py --modis "data\raw\modis\YOUR_MODIS_FILE.csv" --viirs "data\raw\viirs\YOUR_VIIRS_FILE.csv" --root .
python scripts\03_match_sensors.py --root . --time-hours 3 --buffer-km 0.5
python scripts\04_build_analytics.py --root .
echo.
echo FireScope pipeline finished. Check reports\audit and reports\analytics.
pause
