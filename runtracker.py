from flask import Flask
from flask import render_template
from flask import request
from flask import make_response
from flask import redirect
from flask import redirect, session
from ConfigParser import SafeConfigParser
from stravalib import Client

import requests
import json
import sys
import re
import datetime
import pprint
import os.path
import glob

# ---- ---- ---- ----

# Find fastest subtrack
def findFastestTrack(trackLen, cumTime, cumDistance, heartrate, cadence):
	# trackLen = length to look for (typically 1000 m)
	# cumTime = list of datapoints containing seconds, like 2, 5, 8, 15, ...
	# cumDistance = list with data points containing distances in m. like 4, 15, 25, 46,...
	# heartRate = List with heart measurements, like 140, 142, 144, 138
	# cadence = List with cadence's like 75, 76, 74, 78
	# In this above example at t=8 s., we are at 25 m., having a heart beat of 144 and a cadence of 74

	p1 = 0 # data point1 or index1, this will be the start pointer to the fastest subtrack 
	p2 = 1 # data point2 or index2, this will be the end pointer to the fastest substrack
	x = 0  # data point 1 fastest track so far
	y = 1  # data point 2 fastest track so far
	
	maxDistance = cumDistance[-1]  # cumDistance[-1] is the total track length
	minTime = 99999                # best time found so far
	maxLen = len(cumDistance) - 1  # number of datapoints of to track to search in
	
	if trackLen > maxDistance:     # requested subtrack is larger than track
		return(0, 0, 0, 0, 0)
	
	# while maxDistance - cumDistance[p2] > trackLen:
	while p2 < maxLen:
		while ( ( p2 < maxLen ) and (cumDistance[p2] - cumDistance[p1] < trackLen) ):
			p2 = p2 + 1
			
		thisTime = cumTime[p2] - cumTime[p1]
		if thisTime < minTime:
			minTime = thisTime
			x = p1
			y = p2
			
		p1 = p1 +1

	return(x, y, minTime, wAvg(heartrate, cumTime, p1, p2), wAvg(cadence, cumTime, x, y))

# Calc weighted average
def wAvg(thisList, time, p1, p2):
		# Weighted average: weight is time (delta) before measurement
		# Time and thisList are both lists. The time determines the weight.
		#   Example: thisList: 100, 220, 100, time: 1,2,4
		#   Weigthed avg is: ( 1x100 + 1x120 + 2x80 ) / 4
		
		thisWeight = 0
		thisAvg = 0

		for i in range (p1, p2):
			if i: 
				interval = (time[i] - time[i-1]) # begin of list so list[i-1] does not exist
			else: 
				interval = time[i] # begin of list so list[i-1] does not exist
			
			thisWeight = thisWeight + interval
			thisAvg = thisAvg + interval * thisList[i]

		return( thisAvg / thisWeight )

# Format integer to hh:mm:ss string
def mmss(seconds):
	# return formatted string hh:mm:ss
	if seconds < 3600:
		string = "%02d:%02d" % divmod(int(seconds+0.5), 60) 
	else:
		hh=0
		while seconds>=3600:
			seconds=seconds-3600
			hh=hh+1
		mm, ss = divmod(int(seconds+0.5), 60)
		string = "%d:%02d:%02d" % ( hh,mm,ss )

	return( string )	
 
# Prepare data for the zone graphs (Heart Rate Zones, Page Zones, Cadence Zone and Stride Zones)
def getZoneData(thisZones, cumTimeinZone, moveTime, iteration ):
 	thisZonesPlus = thisZones + [999]
	dataZones = []
	highLight = 0
	
	last = iteration[-2:] # define top two most zones
	
	for i in iteration: # 6, 5, 4, ...
	 	timePrc = float( cumTimeinZone[i]*100.0 / moveTime )
		if (i in last) and timePrc >= 10: # If we are in the top zones and have more than 10%, highlight
			highLight = 1

		# Based on this data the graph will be printed			
		dataZones.append({ 'hl': highLight, 'i': i, 'z1mmss': mmss(thisZones[i]), 'z2mmss': (mmss(thisZonesPlus[i+1])), 'z1': thisZones[i], 'z2': thisZonesPlus[i+1], 'timeprcstr': "%4.1f" % (timePrc), 'timeprc': min(78,int((timePrc)+0.5)), 'timestr': mmss(cumTimeinZone[i]) })

	return(dataZones)

# clean data, remove outliers and pauses
def filterData(time, distance, heartrate, cadence, moving ):
	# create new list and filter pauses as well as outliers in speed
	
	outlierL = 2  # min outlier 3 km/h
	outlierR = 25 # max outlier 24 km/h
	
	lTime = []
	lDistance = []
	lSpeed = []
	lHr = []
	lCad = []
	lStep = []
	filtered = []
	filt = {}
	
	start = 0 # skip first datapoint if movement is too little or zero
	while (not moving[start] or not distance[start] or distance[start]*3.6/time[start]<=outlierL or distance[start]*3.6/time[start]>=outlierR):
		start=start+1
	
	lTime.append( time[start] )
	lDistance.append( distance[start] )
	lHr.append( heartrate[start] )
	lCad.append( cadence[start] )
	
	start = start + 1
		
	for i in range(start, len(time)):
		dDistance = distance[i] - distance[i-1]
		dTime = time[i] - time[i-1]
		if ( dTime>0 and moving[i] ):
			dSpeed = dDistance * 3.6 / dTime # speed for this interval in km/h
			if ( dSpeed > outlierL and dSpeed < outlierR ):
				lTime.append( lTime[-1] + dTime )
				lSpeed.append( dSpeed )
				lDistance.append( lDistance[-1] + dDistance )
				lHr.append( heartrate[i] )
				lCad.append( cadence[i] )
				if cadence[i] > 0:
					#lStep.append( dDistance*100 / (cadence[i]*2*dTime/60) )
					lStep.append( dDistance*3000 / (cadence[i]*dTime) )
				else:
					lStep.append( 0 )
			else:
				filtered.append(i)
				filt[i]=dTime
		else:
			filtered.append(i)
			filt[i]=dTime
				
		# endif no move,skip data point			
	
	# return lists:
	
	# cumulative time in s, cumulative distances in m,
	# speed in km/h over last interval, heart rate at this time, cadence oer last interval,
	# step size in m. over last interval,
	
	# filtered datapoints (indexes), time filtered
	#   ex. filt={ 101: 6 } and filtered = [101], meaning at 101 seconds from start we filtered 6 seconds
	
	return(lTime, lDistance, dSpeed, lHr, lCad, lStep, filtered, filt) 

# init new empty list as big as input list
# used to fill measurements not recorded f.e. heart Rate and fill them with 0's
def initList(list):
	newList = []
	for i in range(len(list)):
		newList.append(0)
	return(newList)
	
# Main routine to start analysing data
def analyseActivity(user, header, id, name, date, split):
	
	json_data = getStravaTrackDetails(user,id)
	
	printDate = datetime.datetime(*map(int, re.split('[^\d]', date)[:-1]))
	hrZone = initList(hrZones)
	paceZone = initList(paceZones)
	cadZone = initList(cadZones)
	stepZone = initList(stepZones)
		
	data = {}
	for element in json_data:
		data[element["type"]] = element["data"]
	
	if 'cadence' not in data.keys():
		data['cadence'] = initList(data['time'])
		
	if 'heartrate' not in data.keys():
		data['heartrate'] = initList(data['time'])

	# filter the data, remove outliers and pauses in track.
	(lTime,lDistance,lSpeed,lHr,lCad,lStep,filtered,filt) = filterData(data['time'],data['distance'],data['heartrate'],data['cadence'],data['moving'])

	# *** SECTION 1 *** General section in detailed view
	#  Difference in time filtered and unfiltered is out non-moving time.
	notMoving = data['time'][-1] - lTime[-1]

	tRunName = name
	tRunId = str(id)
	tRunDate = str(printDate).split(' ') #list with date and time
	tTotTrackLen = "%4.2f" % ( lDistance[-1]/1000 )
	tTotTime = "%s (Pause: %s, Moving: %s)" % ( mmss(lTime[-1]+notMoving), mmss(notMoving), mmss(lTime[-1] ) )
	#tTotPace = 	"%s (%2.2f km/h)" % ( mmss( (lTime[-1]) *1000/lDistance[-1] ), 3600 / ( (lTime[-1]) *1000/lDistance[-1]) )
	tTotPace = 	"%s" % ( mmss( (lTime[-1]) *1000/lDistance[-1] ) )
	tAvgHeartrate = "%3s (max %3s)" % ( ( wAvg(lHr, lTime, 0, len(lHr)-1 ) ), ( max(lHr) ) )
	tAvgCadence = "%3s (max %3s)" %   ( ( wAvg(lCad, lTime, 0, len(lCad)-1 )*2 ), ( max(lCad) * 2 ) )
	tAvgStep = "%2.2f (max %2.2f)" %  ( ( wAvg(lStep, lTime, 0, len(lStep)-1 ) ), ( max(lStep) ) )

	# *** SECTION 2 *** track section in detailed view
	trackList=[]
	for trackLen in [ 100, 400, 800, 1000, 1600, 3000, 5000, 6000, 6437, 10000, 16093, 21098]:
		(x, y, minTime, avgHRTrack, avgCad) = findFastestTrack(trackLen, lTime, lDistance, lHr, lCad )
		if minTime <> 0: # if requested subtrack does not exceed track length
			pace = mmss(int((minTime*1000)/(lDistance[y]-lDistance[x])+0.5))
			p1 = int((lDistance[x]/lDistance[-1]*100)+0.5) # percentage begin track
			p2 = int((lDistance[y]/lDistance[-1]*100)+0.5) # percentage end track

			sumFlt=0
			numFlt=0
			# filt is dictionary[index, seconds] with indexes referring to the sequence of the main data set
			# just before the point filtered; seconds contains the filtered #seconds.
			for key in ({ k:v for (k,v) in filt.items() if (k>=x and k<=y) }):
				sumFlt=sumFlt+filt[key]
				numFlt=numFlt+1
		
			trackList.append({ 'tracklen': trackLen, 'p1': p1, 'p2': p2-p1, 'pace': pace, 'mintime': mmss(minTime), 'avghr': avgHRTrack, 'minhr': min(lHr[x:y]), 'maxhr': max(lHr[x:y]), 'avgcad': avgCad*2, 'filtered': sumFlt })

	# *** SECTION 3 ***  prepare the frequency diagrams
	for i in range( 1, len(lTime)-1 ):
		dTime = lTime[i] - lTime[i-1]
		dDistance = lDistance[i] - lDistance[i-1]
		dSpeed = dDistance * 3.6 / dTime # speed for this interval in km/h		
		dPace = 3600 / dSpeed             # pace for this interval (delta)
			
		for j in reversed(range(len(paceZones))):
			if dPace > paceZones[j]: # if pace in this interval belongs to this zone
				paceZone[j] = paceZone[j] + dTime # count seconds in this zone
				break
		for j in reversed(range(len(hrZones))): # for i in [6, 5, 4,...]
			if lHr[i] > hrZones[j]: # if heart rate in this interval belongs to this zone
				hrZone[j] = hrZone[j] + dTime # count seconds in this zone
				break
		for j in reversed(range(len(cadZones))):
			if lCad[i] * 2 > cadZones[j]: # if steps per minute (=cadence*2) in this interval belongs to this zone
				cadZone[j] = cadZone[j] + dTime # count seconds in this zone
				break
		for j in reversed(range(len(stepZones))):
			if lStep[i] > stepZones[j]: # if steps per minute (=cadence*2) in this interval belongs to this zone
				stepZone[j] = stepZone[j] + dTime # count seconds in this zone
				break		
		
	# convert data into HTML data for the graphs
	tPaceZones = getZoneData(paceZones, paceZone, lTime[-1], range(len(paceZones))[::-1] )
	tHrZones =( getZoneData(hrZones, hrZone, lTime[-1], range(len(hrZones)) ) )
	tCadZones =( getZoneData(cadZones, cadZone, lTime[-1], range(len(cadZones)) ) )
	tStepZones =( getZoneData(stepZones, stepZone, lTime[-1], range(len(stepZones)) ) )
	
	# *** SECTION 4 *** SPLIT time part
	
	# Split time / Half Times
	interval = int((lDistance[-1]/2)+0.5)
	hSpeed = avgSpeedperTrack(lDistance, lTime, interval, lHr)

	# Quarter Splits
	interval = int((lDistance[-1]/4)+0.5)
	qSpeed = avgSpeedperTrack(lDistance, lTime, interval, lHr)
	
	# Splits - default 1000 m.
	interval = int(split)
	kmSpeed = avgSpeedperTrack(lDistance, lTime, interval, lHr)

	return( render_template('details.html', user=user, tTrackList=trackList, tPaceZones=tPaceZones, tHrZones=tHrZones, tCadZones=tCadZones, tStepZones=tStepZones, tRunName=tRunName, tRunId = tRunId, tRunDate=tRunDate, tTotTrackLen=tTotTrackLen, tTotTime=tTotTime, tTotPace=tTotPace, tAvgHeartrate=tAvgHeartrate, tAvgCadence=tAvgCadence, tAvgStep=tAvgStep, hSpeed=hSpeed, qSpeed=qSpeed, kmSpeed=kmSpeed, tSplit=split ) )

# Determine average speed per x meter (used for split overview in main detailed screen, section 4)
def avgSpeedperTrack(distance, time, interval, hr):
	
	
	thisInterval = 1
	prev = 0
	iSpeed = []
	iTime = []
	avgSpeed = 1000*time[-1]/distance[-1]
	
	for i in range(len(distance)):
		if distance[i] > (thisInterval * interval):

			if prev:
				dTime = time[i] - time[prev]
				dDistance = distance[i] - distance[prev]
			else:
				dTime = time[i]
				dDistance = distance[i]
				
			dSpeed = 1000*dTime/dDistance
			iHr = wAvg(hr, time, prev, i)
			
			deviation = "%3.1f" % ( (dSpeed -avgSpeed)*dDistance/1000 )
			
			iSpeed.append( { 'i': thisInterval, 'dev': deviation, 'dDistance': int(dDistance+0.5), 'distance': distance[i], 'dTime': dTime, 'dSpeed': dSpeed, 'dTimeStr': mmss(dTime), 'dSpeedStr': mmss(dSpeed), 'faster': (dSpeed<=avgSpeed), 'hr': iHr, 'hi_low': 0 } )

			prev = i
			thisInterval = thisInterval + 1
	
	
	dTime = time[i] - time[prev]
	if dTime:
		dDistance = distance[i] - distance[prev]
		dSpeed = 1000*dTime/dDistance
		iHr = wAvg(hr, time, prev, i)
		
		deviation = "%3.1f" % ( (dSpeed -avgSpeed)*dDistance/1000 )

		iSpeed.append( { 'i': thisInterval, 'dev': deviation, 'dDistance': int(dDistance+0.5), 'distance': distance[i], 'dTime': dTime, 'dSpeed': dSpeed, 'dTimeStr': mmss(dTime), 'dSpeedStr': mmss(dSpeed), 'faster': (dSpeed<=avgSpeed), 'hr': iHr, 'hi_low': 0 } )
	
	low, hi, lowi, hii = 999, 0, 0, 0
	
	for i in range(len(iSpeed)):
		if iSpeed[i]['dSpeed'] < low:
			low = iSpeed[i]['dSpeed']
			lowi = i
		if iSpeed[i]['dSpeed'] > hi:
			hi = iSpeed[i]['dSpeed']
			hii= i
	
	iSpeed[lowi]['hi_low'] = -1
	iSpeed[hii]['hi_low'] = 1
	
	return (iSpeed)
		
# create list page (with totals)
def createList(json_data, user, type):
	# create two HTML blocks for 'list'
	#  one block (body) is the main list, the other block shows totals of the last 6 weeks and months.
	
	weekday = ['Mo','Tu','We','Th','Fr','Sa','Su']
	Months = ['Jan', 'Feb', 'Mrt', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
	HTML_Body = ""
	totalsMonth = {}
	totalsWeek = {}

	for item in json_data:
		if item['type'] == 'Run':
			if ( int(type) == 0 or item['workout_type'] == int(type) ):
				runDate = datetime.datetime(*map(int, re.split('[^\d]', item['start_date_local'])[:-1]))
				tWeekDay = weekday[runDate.weekday()]
				tRunDate = runDate.strftime("%d %b %Y, %H:%M")
				tRunPace = mmss(1000/item['average_speed'])
				tDistance = "%3.1f" % ( item['distance']/1000 )
				tMovingTime = mmss(item['moving_time'])
				
				# This part is to calculate totals per year-month
				yearMonth = str(runDate.year)+" "+str( "%02d" % runDate.month )
				if yearMonth not in totalsMonth.keys():
					totalsMonth[yearMonth] = 0
				totalsMonth[yearMonth] = totalsMonth[yearMonth] + item['distance']
				
				yearWeek  = str(runDate.year)+" "+str( "%02d" % (runDate.isocalendar()[1]) )
				if yearWeek not in totalsWeek.keys():
					totalsWeek[yearWeek] = 0
				totalsWeek[yearWeek] = totalsWeek[yearWeek] + item['distance']
				
				# Does the cache contains this activity?
				tCache = getActivityCashed(user, item['id'])

				HTML_Body =  HTML_Body + render_template('list_simple_body.html', item=item, tMovingTime=mmss(item['moving_time']), tRunDate=tRunDate, tRunPace=tRunPace, tDistance=tDistance, tWeekDay=tWeekDay, tCache=tCache, user=user )
	
	lMonthTots = []
	for i in reversed(sorted(totalsMonth.keys())):
		thisMonth = int(i.split()[1])
		lMonthTots.append([ Months[thisMonth-1], int(totalsMonth[i]/1000+0.5) ])
		if len(lMonthTots) == 6:
			break
			
	lWeekTots = []
	for i in reversed(sorted(totalsWeek.keys())):

		thisWeek = int(i.split()[1])
		lWeekTots.append([ thisWeek, "%4.1f" % (totalsWeek[i]/1000) ])
		if len(lWeekTots) == 6:
			break

	HTML_Tots = render_template('list_simple_totals.html', lMonthTots = lMonthTots, lWeekTots=lWeekTots)

	return(HTML_Body, HTML_Tots)

# create overview page and use cached details to enrich overview (fastest 1000 m. after 25%)
def createXList(json_activity, user, type):
	# Create overview page

	weekday = ['Mo','Tu','We','Th','Fr','Sa','Su']
	HTML = ""
	tTrack=[ "", "" ]
	tAverageHr = 0
	path = 'cache/'+user+'/'
	
	for item in json_activity:
		if item['type'] == 'Run':
			if ( int(type) == 0 or item['workout_type'] == int(type) ):
				runDate = datetime.datetime(*map(int, re.split('[^\d]', item['start_date_local'])[:-1]))
				tWeekDay = weekday[runDate.weekday()]
				tRunDate = runDate.strftime("%d %b %Y, %H:%M")
				tRunPace = mmss(1000/item['average_speed'])
				tDistance = "%3.1f" % ( item['distance']/1000 )
				tMovingTime = mmss(item['moving_time'])
				
				jsonFileName = os.path.join(path, "strava"+str(item['id'])+"-d.json")
				
				if os.path.isfile(jsonFileName):
					file = open(jsonFileName, "r")
					json_detail = json.load(file)
					file.close()
					
					data = {}
					for element in json_detail:
						data[element["type"]] = element["data"]
					if 'cadence' not in data.keys():
						data['cadence'] = initList(data['time'])
					if 'heartrate' not in data.keys():
						data['heartrate'] = initList(data['time'])
					if 'average_heartrate' in item.keys():
						tAverageHr = int(item['average_heartrate']+0.5)

					(lTime,lDistance,lSpeed,lHr,lCad,lStep,filtered,filt) = filterData(data['time'],data['distance'],data['heartrate'],data['cadence'],data['moving'])
					notMoving = data['time'][-1] - lTime[-1]
					hl = len(lTime) / 4
					(x, y, minTime, avgHRTrack, avgCad) = findFastestTrack(1000, lTime[hl:], lDistance[hl:], lHr[hl:], lCad[hl:] )
					tTrack = [ mmss(minTime), avgHRTrack ]
					
				
				HTML =  HTML + render_template('overview.html', item=item, tRunDate=tRunDate, tRunPace=tRunPace, tDistance=tDistance, tWeekDay=tWeekDay, tAverageHr=tAverageHr, tMovingTime=tMovingTime, tPause=mmss(notMoving), tTrack=tTrack )
	
	return(HTML)

# All functions get* do get data form Strava (or cache)

# read cookie or call Strava to determine my userID and show list
def getStravaUserID():
	if 'stravaUserID' in request.cookies:
		user = request.cookies.get("stravaUserID")
		response = make_response( redirect('/list?user='+str(user)) )
	else:
		url = 'https://www.strava.com/api/v3/athlete'
		json_data = requests.get(url, headers=header).json()
		user = str(json_data['id'])
		response = make_response( redirect('/list?user='+user) )
		response.set_cookie('stravaUserID', str(user) )

	return(response)


# get list of activities form Stava or cache
def getStravaList(readCache, user):
	if header == '':
		a=1/0 # Header not defined

	path = 'cache/'+user
	if not os.path.exists(path):
		os.mkdir(path) 
	
	url = 'https://www.strava.com/api/v3/athlete/activities/?per_page=100'
	jsonFileName = os.path.join(path, "list.json")
	
	if os.path.isfile(jsonFileName) and readCache:
		file = open(jsonFileName, "r")
		json_data = json.load(file)
		file.close()
	else:
		json_data = requests.get(url, headers=header).json()
		file = open(jsonFileName,"w")
		json.dump(json_data, file)
		file.close()

	if len(json_data) < 5:
		a=1/0 # TODO invalid JSON data (list.json) could be from cache or from Strava
		
	return(json_data)


# 
def getCachedActivities(user):
	path = 'cache/'+user+'/'
	json_data =[]
	
	files = filter(os.path.isfile, glob.glob(path + "*a.json"))
	
	files.sort(key=lambda x: x, reverse=True)
	for filename in files:
		if (filename.split("-")[-1] ==  "a.json"): # TODO: this line can be removed?
			file = open( (os.path.join(filename)) , "r")
			json_data.append(json.load(file))

	return(json_data)

# get activity data for detailed view
def getStraveActivity(user, activityId, refresh):

	url = 'https://www.strava.com/api/v3/activities/'+str(activityId)
	path = 'cache/'+user
	
	jsonFileName = os.path.join(path, "strava"+str(activityId)+"-a.json")

	if os.path.isfile(jsonFileName) and (refresh == 0):
		file = open(jsonFileName, "r")
		json_data = json.load(file)
		file.close()
	else:
		json_data = requests.get(url, headers=header).json()
		if len(json_data) > 4:
			file = open(jsonFileName,"w")
			json.dump(json_data, file)
			file.close()
		else:
			# TODO this error is not caught in the calling function!
			a=1/0
			return( render_template('error.html', msg='Activity not found' ) )

	return(json_data)

# Check if activity details are in cache
def getActivityCashed(user, actId):
	path = 'cache/'+user
	jsonFileName = os.path.join(path, "strava"+str(actId)+"-d.json")
	if os.path.isfile(jsonFileName):
		return(1)
	else:
		return(0)

# Get activity details from Strava or cache
def getStravaTrackDetails(user,actId):
	path = 'cache/'+user
	jsonFileName = os.path.join(path, "strava"+str(actId)+"-d.json")

	if os.path.isfile(jsonFileName): # read activity from cache or get it from Strava
		file = open(jsonFileName, "r")
		json_data = json.load(file)
		file.close()
	else:
		url = 'https://www.strava.com/api/v3/activities/'+str(actId)+'/streams/time,distance,heartrate,cadence,moving'
		json_data = requests.get(url, headers=header).json()
		if len(json_data) > 3:
			file = open(jsonFileName,"w")
			json.dump(json_data, file)
			file.close()
		else:
			# TODO, this error is not caught in the calling function
			b=1/0
			return("Error, detailed track info fom Strava in wrong or unexpected format")
	
	return(json_data)

# ---- ---- ---- ----

paceZones= [ 0, 220, 240, 260, 280, 300, 330 ]
hrZones  = [ 0,  95, 114, 133, 152, 171, 190 ]
cadZones = [ 0, 140, 150, 155, 160, 165, 170, 175, 180, 185 ]
stepZones= [ 0, 100, 110, 120, 130, 140, 150, 160, 170, 180 ]

# ---- ---- ---- ----

#parser = SafeConfigParser()
#parser.read('auth.ini')
#print parser.sections()
#bearer_id = parser.get('strava', 'bearer_id')

bearer_id = 'ea8bc2be740402a07e55a8dbe27074e66f4d26daXXX'
STRAVA_CLIENT_ID     = '7144'
STRAVA_CALLBACK_URL  = 'http://maxbiss.myqnapcloud.com:8084/auth'
STRAVA_CLIENT_SECRET = '8bface9d2280e2bcef999c692f2433019bc8fd3b'

#header = {'Authorization': 'Bearer {0}'.format(bearer_id)}
#header = {'Authorization': 'Bearer %s' % bearer_id }
header = ''
  
# ---- ---- ---- ----

app = Flask(__name__)

app.secret_key = 'GeHeImPjE!'
client = Client()
token = ''

@app.route('/login')
def login():
	global header
	
	if session.get('access_token', None) is None:
		return redirect(Client().authorization_url(client_id=STRAVA_CLIENT_ID, redirect_uri=STRAVA_CALLBACK_URL, scope="view_private"))
	else:
		token = session.get('access_token')
		header = {'Authorization': 'Bearer {0}'.format(token)}
	
	# return('Login ready '+str(header))
	
	return redirect('/whoami')


@app.route('/auth')
def auth():
	global header
	
	code = request.args.get('code')
	token = Client().exchange_code_for_token(client_id=STRAVA_CLIENT_ID, client_secret=STRAVA_CLIENT_SECRET, code=code)

	header = {'Authorization': 'Bearer {0}'.format(token)}

	if token:
		session['access_token'] = token
		
	url = 'https://www.strava.com/api/v3/athlete'
	json_data = requests.get(url, headers=header).json()
	user = str(json_data['id'])
	return('<HTML> you are user: <a href="/">'+str(user)+'</html>')

	return redirect('/whoami')

# Start screen to confirm login and show menu
@app.route('/whoami')
def whoami():
	url = 'https://www.strava.com/api/v3/athlete'
	json_data = requests.get(url, headers=header).json()
	user = str(json_data['id'])
	
	HTML = render_template('login.html', user=user)
	return(HTML)


@app.route('/')
def start():
	if header == '':
		return redirect('/login')
	return(getStravaUserID())
	
	
@app.route('/hello')
def hello():
	# use to test if Flask is running
	return 'Hello World'


@app.route('/strava')
def strava():
	# show one activity (details)
	if header == '':
		return redirect('/login')
	
	if ( not request.args.has_key('user') ):
		return( make_response( redirect('/') ) )
	
	user = request.args['user']
	
	activityId = 0
	activityId =  request.args['id']
	
	if (request.args.has_key('split')):
		split = request.args['split']
	else:
		split = 1000

	if (request.args.has_key('refresh')):
		refresh = 1
	else:
		refresh = 0

	json_data = getStraveActivity(user, activityId, refresh)

	activityName = json_data['name']
	activityDate = json_data['start_date_local']

	HTML = render_template('header.html', user=user)
	HTML = HTML + analyseActivity(user, header, activityId, activityName, activityDate, split) 
	
	return( HTML )
	

@app.route('/list')
def list():
	# show list of activities and include week- and month totals
	if header == '':
		return redirect('/login')
		
	if ( not request.args.has_key('user') ):
		return( make_response( redirect('/') ) )
	
	user = request.args['user']
	
	readCache = 1
	if (request.args.has_key('refresh')):
		readCache = int(request.args['refresh'])
	if (request.args.has_key('type')):
		type = request.args['type']
	else:
		type = 0
		
	json_data = getStravaList(readCache, user)	
	
	HTML_Header = render_template('header.html', user=user)
	HTML_Body, HTML_Tots = createList(json_data, user, type)
	
	return( render_template('list_simple_frame.html', HTML_Header=HTML_Header, HTML_Body=HTML_Body, HTML_Tots=HTML_Tots) )


@app.route('/cache')
def cache():
	# Show one of the overview pages
	
	if ( not request.args.has_key('user') ):
		return( make_response( redirect('/') ) )
	
	user = request.args['user']
	
	if (request.args.has_key('type')):
		type = request.args['type']
	else:
		type = 0

	json_data = getCachedActivities(user)
	
	HTML = render_template('header.html', user=user)
	HTML = HTML + createXList(json_data, user, type)
		
	return( HTML )


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8084, debug = True)
