import json
import os
from flask import Flask, render_template, request, redirect, url_for, flash
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.jaeger.thrift import JaegerExporter
from opentelemetry.instrumentation.flask import FlaskInstrumentor
from opentelemetry.trace import SpanKind
from collections import defaultdict
requests_count = defaultdict(int)
import time
import logging
from json_log_formatter import JSONFormatter

error_count = defaultdict(int)

# Flask App Initialization
app = Flask(__name__)
app.secret_key = 'secret'
COURSE_FILE = 'course_catalog.json'

# OpenTelemetry Setup
resource = Resource.create({"service.name": "course-catalog-service"})
trace.set_tracer_provider(TracerProvider(resource=resource))
tracer = trace.get_tracer(__name__)
jaeger_exporter = JaegerExporter(
    agent_host_name="localhost",
    agent_port=6831,
)
span_processor = BatchSpanProcessor(jaeger_exporter)
trace.get_tracer_provider().add_span_processor(span_processor)
FlaskInstrumentor().instrument_app(app)


# Utility Functions
def load_courses():
    """Load courses from the JSON file."""
    if not os.path.exists(COURSE_FILE):  # check if file exists
        return []  # return empty list if no file
    with open(COURSE_FILE, 'r') as file:  # open file in read mode
        return json.load(file)  # load and return courses


def save_courses(data):
    """Save new course data to the JSON file."""
    courses = load_courses()  # load existing courses
    courses.append(data)  # add new course to list
    with open(COURSE_FILE, 'w') as file:  # open file in write mode
        json.dump(courses, file, indent=4)  # save updated courses



# Routes
@app.route('/')
def index():
    return render_template('index.html')


@app.route('/catalog')
def course_catalog():
    start_time = time.time()  # measure processing time
    requests_count['catalog'] += 1  # increment route requests count
    
    with tracer.start_as_current_span("render-course-catalog") as span:
        span.set_attribute("http.method", request.method)  # log HTTP method
        span.set_attribute("http.url", request.url)  # log request URL
        span.set_attribute("user.ip", request.remote_addr)  # log user IP
        span.set_attribute("requests.count", requests_count['catalog'])  # log request count
        span.add_event("Loading course catalog")  # log event: catalog loading
        
        courses = load_courses()  # load courses from JSON
        span.set_attribute("total_courses", len(courses))  # log number of courses
        span.set_attribute("processing_time", time.time() - start_time)  # log processing time
        
        logger.info({
            "event": "Page Rendered",  # page render event
            "route": "/catalog",  # accessed route
            "total_courses": len(courses),  # number of courses
            "processing_time": time.time() - start_time  # time taken
        })
        
        return render_template('course_catalog.html', courses=courses)  # render catalog page




@app.route('/add_course', methods=['GET', 'POST'])
def add_course():
    start_time = time.time()  # start timer
    requests_count['add_course'] += 1  # count add requests
    with tracer.start_as_current_span("add-course") as span:
        span.set_attribute("http.method", request.method)  # log HTTP method
        span.set_attribute("http.url", request.url)  # log request URL
        span.set_attribute("user.ip", request.remote_addr)  # log user IP
        span.set_attribute("requests.count", requests_count['add_course'])  # log request count

        if request.method == 'POST':  # check if form submitted
            course = {
                'code': request.form.get('code', '').strip(),  # get course code
                'name': request.form.get('name', '').strip(),  # get course name
                'instructor': request.form.get('instructor', '').strip(),  # get instructor
                'semester': request.form.get('semester', '').strip(),  # get semester
                'schedule': request.form.get('schedule', '').strip(),  # get schedule
                'classroom': request.form.get('classroom', '').strip(),  # get classroom
                'prerequisites': request.form.get('prerequisites', '').strip(),  # get prerequisites
                'grading': request.form.get('grading', '').strip(),  # get grading info
                'description': request.form.get('description', '').strip()  # get description
            }

            if not course['code'] or not course['name'] or not course['instructor']:  # check required fields
                error_count['add_course'] += 1  # count errors
                span.add_event("Validation failed: Missing required fields")  # log validation error
                span.set_attribute("error_count", error_count['add_course'])  # log error count

                logger.warning({
                    "event": "Form Validation Error",  # log form error
                    "route": "/add_course",  # log route
                    "error": "Missing required fields"  # log error reason
                })

                flash('Course Code, Course Name and Instructor are required!', 'error')  # show error
                return render_template('add_course.html')  # reload form

            save_courses(course)  # save course data
            span.add_event("Course saved successfully")  # log save success
            span.set_attribute("processing_time", time.time() - start_time)  # log time taken
            logger.info({
                "event": "Course Added",  # log add event
                "course_code": course['code'],  # log course code
                "course_name": course['name']  # log course name
            })
            flash(f"Course '{course['name']}' added successfully!", "success")  # show success message
            return redirect(url_for('course_catalog'))  # go to catalog

        return render_template('add_course.html')  # show add form



# Just added a delete button to remove the unneccessary courses added
@app.route('/delete_course/<code>', methods=['POST'])
def delete_course(code):
    courses = load_courses()  # load all courses
    updated_courses = [course for course in courses if course['code'] != code]  # remove matching course
    
    with open(COURSE_FILE, 'w') as file:  # open JSON file for writing
        json.dump(updated_courses, file, indent=4)  # save updated courses
    
    flash(f"Course with code '{code}' deleted successfully!", "success")  # show success message
    return redirect(url_for('course_catalog'))  # go back to catalog



@app.route('/course/<code>')
def course_details(code):
    start_time = time.time()  # start timer
    with tracer.start_as_current_span("view-course-details") as span:
        span.set_attribute("http.method", request.method)  # log HTTP method
        span.set_attribute("http.url", request.url)  # log request URL
        span.set_attribute("user.ip", request.remote_addr)  # log user IP
        span.set_attribute("course_code", code)  # log course code
        
        courses = load_courses()  # load courses from JSON
        course = next((course for course in courses if course['code'] == code), None)  # find course
        
        if not course:  # if course not found
            error_count['course_details'] += 1  # increment error count
            span.add_event("Course not found")  # log missing course
            span.set_attribute("error_count", error_count['course_details'])  # log error count
            
            logger.error({
                "event": "Course Not Found",  # log event
                "route": "/course/<code>",  # log route
                "course_code": code  # log course code
            })
            
            flash(f"No course found with code '{code}'.", "error")  # show error message
            return redirect(url_for('course_catalog'))  # redirect to catalog
        
        span.add_event("Course details rendered successfully")  # log render success
        span.set_attribute("processing_time", time.time() - start_time)  # log time taken
        
        logger.info({
            "event": "Course Details Rendered",  # log event
            "course_code": course['code'],  # log course code
            "processing_time": time.time() - start_time  # log processing time
        })
        
        return render_template('course_details.html', course=course)  # render course details page




@app.route("/manual-trace")
def manual_trace():
    with tracer.start_as_current_span("manual-span", kind=SpanKind.SERVER) as span:
        span.set_attribute("http.method", request.method)  # log HTTP method
        span.set_attribute("http.url", request.url)  # log request URL
        span.add_event("Processing request")  # log event: request processing
        return "Manual trace recorded!", 200  # return success message


@app.route("/auto-instrumented")
def auto_instrumented():
    return "This route is auto-instrumented!", 200  # auto-instrumented route

# Logging setup
formatter = JSONFormatter()  # use JSON format for logs
handler = logging.FileHandler(filename='app.log')  # log to app.log file
handler.setFormatter(formatter)  # set JSON formatter

logger = logging.getLogger('course_portal')  # create logger
logger.addHandler(handler)  # add file handler to logger
logger.setLevel(logging.INFO)  # set logging level to INFO


if __name__ == '__main__':
    app.run(debug=True)
