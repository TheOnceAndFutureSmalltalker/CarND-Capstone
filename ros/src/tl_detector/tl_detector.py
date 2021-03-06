#!/usr/bin/env python
import rospy
from std_msgs.msg import Int32
from geometry_msgs.msg import PoseStamped, Pose
from styx_msgs.msg import TrafficLightArray, TrafficLight
from styx_msgs.msg import Lane
from sensor_msgs.msg import Image
from cv_bridge import CvBridge
from light_classification.tl_classifier import TLClassifier
import tf
import cv2
import yaml

import math
import numpy as np
from points_organizer import PointsOrganizer

STATE_COUNT_THRESHOLD = 3
IMAGE_CLASSIFICATION_CYCLE = 1

class TLDetector(object):
    def __init__(self):
        rospy.init_node('tl_detector')

        self.pose = None
        self.waypoints = None
        self.waypoints_organizer = None
        self.camera_image = None
        self.lights = []
        self.stop_line_organizer = None

        sub1 = rospy.Subscriber('/current_pose', PoseStamped, self.pose_cb)
        sub2 = rospy.Subscriber('/base_waypoints', Lane, self.waypoints_cb)

        '''
        /vehicle/traffic_lights provides you with the location of the traffic light in 3D map space and
        helps you acquire an accurate ground truth data source for the traffic light
        classifier by sending the current color state of all traffic lights in the
        simulator. When testing on the vehicle, the color state will not be available. You'll need to
        rely on the position of the light and the camera image to predict it.
        '''
        sub3 = rospy.Subscriber('/vehicle/traffic_lights', TrafficLightArray, self.traffic_cb)
        sub6 = rospy.Subscriber('/image_color', Image, self.image_cb, queue_size=1, buff_size=2*52428800)

        config_string = rospy.get_param("/traffic_light_config")
        self.config = yaml.load(config_string)

        self.upcoming_red_light_pub = rospy.Publisher('/traffic_waypoint', Int32, queue_size=1)

        self.bridge = CvBridge()
        self.light_classifier = TLClassifier()
        self.listener = tf.TransformListener()

        self.state = TrafficLight.UNKNOWN
        self.last_state = TrafficLight.UNKNOWN
        self.last_wp = -1
        self.state_count = 0

        self.stop_line_positions = self.config['stop_line_positions']
        self.image_counter = 0

        rospy.spin()

    def pose_cb(self, msg):
        self.pose = msg

    def waypoints_cb(self, waypoints):
        self.waypoints = waypoints
        self.waypoints_organizer = PointsOrganizer(
            [[waypoint.pose.pose.position.x, waypoint.pose.pose.position.y]
             for waypoint in waypoints.waypoints])

    def traffic_cb(self, msg):
        self.lights = msg.lights
        self.stop_line_organizer = PointsOrganizer(
            [[light.pose.pose.position.x, light.pose.pose.position.y] for light in self.lights])

    def image_cb(self, msg):
        self.image_counter += 1
        if IMAGE_CLASSIFICATION_CYCLE > 1 and self.image_counter % IMAGE_CLASSIFICATION_CYCLE != 1:
            return
        """Identifies red lights in the incoming camera image and publishes the index
            of the waypoint closest to the red light's stop line to /traffic_waypoint
        Args:
            msg (Image): image from car-mounted camera
        """
        self.has_image = True
        self.camera_image = msg
        light_wp, state = self.process_traffic_lights()

        '''
        Publish upcoming red lights at camera frequency.
        Each predicted state has to occur `STATE_COUNT_THRESHOLD` number
        of times till we start using it. Otherwise the previous stable state is
        used.
        '''
        if self.state != state:
            self.state_count = 0
            self.state = state
        elif self.state_count >= STATE_COUNT_THRESHOLD:
            self.last_state = self.state
            light_wp = light_wp if state == TrafficLight.RED else -1
            self.last_wp = light_wp
            self.upcoming_red_light_pub.publish(Int32(light_wp))
        else:
            self.upcoming_red_light_pub.publish(Int32(self.last_wp))
        self.state_count += 1

    def get_light_state(self, light):
        """Determines the current color of the traffic light
        Args:
            light (TrafficLight): light to classify
        Returns:
            int: ID of traffic light color (specified in styx_msgs/TrafficLight)
        """
        # For testing just return light state
        return light.state
        """
        if(not self.has_image):
            self.prev_light_loc = None
            return False
        cv_image = self.bridge.imgmsg_to_cv2(self.camera_image, "bgr8")
        #Get classification
        return self.light_classifier.get_classification(cv_image)
        """

    def process_traffic_lights(self):
        """Finds closest visible traffic light, if one exists, and determines its
            location and color
        Returns:
            int: index of waypoint closes to the upcoming stop line for a traffic light (-1 if none exists)
            int: ID of traffic light color (specified in styx_msgs/TrafficLight)
        """
        if self.pose and self.waypoints_organizer and self.stop_line_organizer:
            closest_waypoint_idx = self.waypoints_organizer.get_closest_point_idx(
                self.pose.pose.position.x, self.pose.pose.position.y, look_mode='AHEAD')
            closest_waypoint = self.waypoints.waypoints[closest_waypoint_idx]

            # Getting the closest light ahead of the vehicle
            closest_light_idx = self.stop_line_organizer.get_closest_point_idx(
                closest_waypoint.pose.pose.position.x, closest_waypoint.pose.pose.position.y, look_mode='AHEAD')

            if closest_light_idx is not None:
                closest_light = self.lights[closest_light_idx]
                # Getting the stop line associated with the closest light
                closest_stop_line = self.stop_line_positions[closest_light_idx]

                # Getting the waypoint closest to stop line
                stop_waypoint_idx = self.waypoints_organizer.get_closest_point_idx(
                    closest_stop_line[0], closest_stop_line[1], look_mode='AHEAD')

                state = self.get_light_state(closest_light)
                return stop_waypoint_idx, state

        return -1, TrafficLight.UNKNOWN


if __name__ == '__main__':
    try:
        TLDetector()
    except rospy.ROSInterruptException:
        rospy.logerr('Could not start traffic node.')
