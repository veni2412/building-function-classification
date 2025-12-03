"""
QGIS Model: Compute Nearest Edge-to-Edge Distance Between Polygons
Without Crossing Roads

This model finds the nearest polygon from a buildings layer, ensuring
the connecting line does not cross any road features.

Inputs:
- Buildings Layer (Polygon)
- Roads Layer (LineString/Polygon)

Output:
- Buildings layer with new field 'nearest_dist' containing the distance
  to the nearest building that doesn't require crossing a road

Algorithm Steps:
1. Extract vertices from buildings to get edge points
2. Create Voronoi polygons to identify proximity zones
3. For each building, find candidates within search radius
4. Create connecting lines between building boundaries
5. Filter lines that intersect with roads
6. Calculate minimum distance from remaining valid connections
"""

from qgis.core import (QgsProcessing, QgsProcessingAlgorithm,
                       QgsProcessingParameterVectorLayer,
                       QgsProcessingParameterNumber,
                       QgsProcessingParameterFeatureSink,
                       QgsFeature, QgsGeometry, QgsPointXY,
                       QgsField, QgsFields, QgsSpatialIndex,
                       QgsFeatureRequest, QgsWkbTypes)
from qgis.PyQt.QtCore import QVariant
from qgis import processing

class NearestDistanceNoRoadCrossing(QgsProcessingAlgorithm):
    
    BUILDINGS = 'BUILDINGS'
    ROADS = 'ROADS'
    SEARCH_RADIUS = 'SEARCH_RADIUS'
    OUTPUT = 'OUTPUT'
    
    def initAlgorithm(self, config=None):
        # Input buildings layer
        self.addParameter(
            QgsProcessingParameterVectorLayer(
                self.BUILDINGS,
                'Buildings Layer',
                [QgsProcessing.TypeVectorPolygon]
            )
        )
        
        # Input roads layer
        self.addParameter(
            QgsProcessingParameterVectorLayer(
                self.ROADS,
                'Roads Layer',
                [QgsProcessing.TypeVectorLine, QgsProcessing.TypeVectorPolygon]
            )
        )
        
        # Search radius parameter
        self.addParameter(
            QgsProcessingParameterNumber(
                self.SEARCH_RADIUS,
                'Maximum Search Radius (map units)',
                type=QgsProcessingParameterNumber.Double,
                defaultValue=100.0,
                minValue=0.0
            )
        )
        
        # Output layer
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT,
                'Buildings with Nearest Distance'
            )
        )
    
    def processAlgorithm(self, parameters, context, feedback):
        # Get input layers
        buildings_layer = self.parameterAsVectorLayer(parameters, self.BUILDINGS, context)
        roads_layer = self.parameterAsVectorLayer(parameters, self.ROADS, context)
        search_radius = self.parameterAsDouble(parameters, self.SEARCH_RADIUS, context)
        
        # Create output fields
        fields = buildings_layer.fields()
        fields.append(QgsField('nearest_id', QVariant.Int))
        fields.append(QgsField('nearest_dist', QVariant.Double))
        
        # Create output sink
        (sink, dest_id) = self.parameterAsSink(
            parameters, self.OUTPUT, context,
            fields, buildings_layer.wkbType(), buildings_layer.crs()
        )
        
        # Build spatial index for buildings
        building_index = QgsSpatialIndex()
        building_features = {}
        for feature in buildings_layer.getFeatures():
            building_index.insertFeature(feature)
            building_features[feature.id()] = feature
        
        # Build spatial index for roads
        road_index = QgsSpatialIndex()
        road_features = {}
        for feature in roads_layer.getFeatures():
            road_index.insertFeature(feature)
            road_features[feature.id()] = feature
        
        total = buildings_layer.featureCount()
        
        # Process each building
        for current, source_feature in enumerate(buildings_layer.getFeatures()):
            if feedback.isCanceled():
                break
            
            feedback.setProgress(int(current * 100 / total))
            
            source_geom = source_feature.geometry()
            source_bbox = source_geom.boundingBox()
            source_bbox_buffered = source_bbox.buffered(search_radius)
            
            # Find candidate buildings within search radius
            candidate_ids = building_index.intersects(source_bbox_buffered)
            
            min_distance = float('inf')
            nearest_id = None
            
            for candidate_id in candidate_ids:
                # Skip self
                if candidate_id == source_feature.id():
                    continue
                
                target_feature = building_features[candidate_id]
                target_geom = target_feature.geometry()
                
                # Calculate distance
                distance = source_geom.distance(target_geom)
                
                # Skip if beyond search radius
                if distance > search_radius or distance >= min_distance:
                    continue
                
                # Create line between closest points
                closest_line = self.create_shortest_line(source_geom, target_geom)
                
                # Check if line crosses any road
                if not self.crosses_road(closest_line, road_index, road_features):
                    min_distance = distance
                    nearest_id = candidate_id
            
            # Create output feature
            out_feature = QgsFeature(fields)
            out_feature.setGeometry(source_geom)
            
            # Copy original attributes
            for i, field in enumerate(buildings_layer.fields()):
                out_feature.setAttribute(field.name(), source_feature.attribute(field.name()))
            
            # Add new attributes
            out_feature.setAttribute('nearest_id', nearest_id if nearest_id is not None else -1)
            out_feature.setAttribute('nearest_dist', min_distance if min_distance != float('inf') else -1)
            
            sink.addFeature(out_feature)
        
        return {self.OUTPUT: dest_id}
    
    def create_shortest_line(self, geom1, geom2):
        """Create a line geometry between the closest points of two geometries"""
        # Get the shortest line between geometries
        shortest_line = geom1.shortestLine(geom2)
        return shortest_line
    
    def crosses_road(self, line_geom, road_index, road_features):
        """Check if a line geometry crosses any road"""
        # Get candidate roads that might intersect
        line_bbox = line_geom.boundingBox()
        candidate_road_ids = road_index.intersects(line_bbox)
        
        for road_id in candidate_road_ids:
            road_geom = road_features[road_id].geometry()
            
            # Check for intersection
            if line_geom.intersects(road_geom):
                # Make sure it's a crossing (not just touching)
                intersection = line_geom.intersection(road_geom)
                if intersection and not intersection.isEmpty():
                    # Check if intersection is more than just a point
                    # (could be touching at endpoint)
                    if intersection.type() == QgsWkbTypes.LineGeometry:
                        return True
                    # If point intersection, check if it's internal
                    elif intersection.type() == QgsWkbTypes.PointGeometry:
                        # Check if intersection point is on the line interior
                        line_points = [line_geom.asPolyline()[0], line_geom.asPolyline()[-1]]
                        int_point = intersection.asPoint()
                        # If intersection point is not an endpoint, it crosses
                        epsilon = 0.0001
                        is_endpoint = any(
                            abs(int_point.x() - pt.x()) < epsilon and 
                            abs(int_point.y() - pt.y()) < epsilon 
                            for pt in line_points
                        )
                        if not is_endpoint:
                            return True
        
        return False
    
    def name(self):
        return 'nearestdistancenoroadcrossing'
    
    def displayName(self):
        return 'Nearest Distance Without Road Crossing'
    
    def group(self):
        return 'Spatial Analysis'
    
    def groupId(self):
        return 'spatialanalysis'
    
    def createInstance(self):
        return NearestDistanceNoRoadCrossing()
    
    def shortHelpString(self):
        return """
        This algorithm computes the nearest edge-to-edge distance between 
        polygons in a buildings layer, considering only buildings that can 
        be reached without crossing any road features.
        
        Parameters:
        - Buildings Layer: Polygon layer containing building features
        - Roads Layer: Line or polygon layer containing road features
        - Search Radius: Maximum distance to search for nearest buildings
        
        Output:
        - Buildings layer with two new fields:
          * nearest_id: ID of the nearest building (or -1 if none found)
          * nearest_dist: Distance to nearest building (or -1 if none found)
        
        The algorithm creates a line between each building pair and checks
        if it intersects with any road. Only buildings reachable without
        crossing roads are considered as candidates.
        """