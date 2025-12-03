import geopandas as gpd
import pandas as pd

def classify_land_use(row):
    """
    Classify land use based on decision tree logic.
    
    Expected columns:
    - MotorwayBuffer (boolean or 0/1)
    - StreetAngle (float, in degrees)
    - PrimarySecondary (boolean or 0/1)
    - Frontage (float, 0-1 range)
    - ServiceBuffer (boolean or 0/1)
    - Compactness (float)
    - Area (float)
    - Corners (int)
    - ERI (float, Elongation Ratio Index)
    """
    
    # Node A: Motorway Buffer?
    if row['Motorway']:
        return 'Non Residential'
    
    # Node C: StreetAngle > 20°?
    if row['Closest'] > 20:
        return 'Residential'
    
    # Node E: Primary / Secondary?
    if row['PrimarySecondary']:
        # Node F: Frontage < 0.2?
        if row['frontage_ratio'] < 0.2:
            return 'Non Residential'
        else:
            return 'Mixed'
    else:
        # Node I: Frontage < 0.2?
        if row['frontage_ratio'] < 0.2:
            return 'Non Residential'
        
        # Node K: Service Buffer?
        if row['Service']:
            # Node L: Frontage < 0.2?
            if row['frontage_ratio'] < 0.2:
                return 'Non Residential'
            else:
                return 'Mixed'
        
        # Node O: Compactness < 0.62?
        if row['Compactness'] < 0.62:
            # Node P: Area > 200 OR Corners > 4 OR ERI < 0.9?
            if row['Area'] > 200 or row['Corners'] > 4 or row['ERI'] < 0.9:
                return 'Non Residential'
            else:
                return 'Residential'
        else:
            # Node S: Frontage > 0.5?
            if row['frontage_ratio'] > 0.5:
                # Node T: Corners > 4 OR ERI < 0.9?
                if row['Corners'] > 4 or row['ERI'] < 0.9:
                    return 'Mixed'
                else:
                    return 'Residential'
            else:
                # Node W: Area > 200 OR Corners > 4 OR ERI < 0.9?
                if row['Area'] > 200 or row['Corners'] > 4 or row['ERI'] < 0.9:
                    return 'Non Residential'
                else:
                    return 'Residential'


def process_gpkg(input_path, output_path=None):
    """
    Load GeoPackage, apply decision tree classification, and save results.
    
    Parameters:
    -----------
    input_path : str
        Path to input GeoPackage file
    output_path : str, optional
        Path to save output GeoPackage. If None, adds '_classified' to input name
    
    Returns:
    --------
    geopandas.GeoDataFrame
        GeoDataFrame with added 'prediction' column
    """
    
    # Load the GeoPackage
    print(f"Loading {input_path}...")
    gdf = gpd.read_file(input_path)
    
    # Required columns
    required_cols = [
        'MotorwayBuffer', 'StreetAngle', 'PrimarySecondary', 
        'Frontage', 'ServiceBuffer', 'Compactness', 
        'Area', 'Corners', 'ERI'
    ]
    
    # Check for missing columns
    missing_cols = [col for col in required_cols if col not in gdf.columns]
    if missing_cols:
        raise ValueError(f"Missing required columns: {missing_cols}")
    
    # Apply classification
    print("Applying decision tree classification...")
    gdf['prediction'] = gdf.apply(classify_land_use, axis=1)
    
    # Print summary statistics
    print("\nClassification Summary:")
    print(gdf['prediction'].value_counts())
    print(f"\nTotal polygons classified: {len(gdf)}")
    
    # Save results
    if output_path is None:
        output_path = input_path.replace('.gpkg', '_classified.gpkg')
    
    print(f"\nSaving results to {output_path}...")
    gdf.to_file(output_path, driver='GPKG')
    print("Done!")
    
    return gdf


# Example usage
if __name__ == "__main__":
    # Replace with your actual file path
    input_file = "Data.gpkg"
    
    # Process the file
    result_gdf = process_gpkg(input_file)
    
    # Optional: specify custom output path
    # result_gdf = process_gpkg(input_file, "custom_output.gpkg")