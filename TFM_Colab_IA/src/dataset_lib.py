import os
import difflib
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

def validate_and_correct_label(label, valid_labels, debug=False):
    """
    Validates and corrects a label based on the list of valid classes.
    It uses fuzzy matching to correct misspellings.
    Args:
        label: The label to validate and correct.
        valid_labels: List of valid labels.
        debug: Information about the file (used for logging/debugging, currently not used in logic).
    Returns:
        The corrected label if found, None otherwise.
    """
    label_str = str(label).strip()
    if label_str in valid_labels: 
        return label_str
    match = difflib.get_close_matches(label_str, valid_labels, n=1, cutoff=0.6)
    return match[0] if match else None

def load_sensor_data(file_path, window_size, features_per_sensor):
    """
    Loads and processes data for a specific sensor from a CSV file.
    Args:
        file_path: Path to the sensor CSV file.
        window_size: Number of samples per window.
        features_per_sensor: Number of features per sensor.
    Returns:
        tuple: (data, raw_labels) or (None, None) if the file is missing or invalid.
    """
    # Skip the session if any required sensor data is missing
    if not os.path.exists(file_path): 
        return None, None

    # Load sensor data from CSV
    df = pd.read_csv(file_path, header=None)
    
    # Verify expected number of columns (timestamp + 600 features + label)
    if df.shape[1] != 602: 
        return None, None
    
    # Remove any rows containing NaN values
    df = df.dropna()

    # Extract the raw labels (column index 601)
    raw_labels = df.iloc[:, 601].values
    
    # Extract the 600 features (200 X, 200 Y, 200 Z) and reshape
    data = df.iloc[:, 1:601].values.reshape(-1, window_size, features_per_sensor)
    
    return data, raw_labels

def compute_functionals(data, raw_labels):
    """
    Computes a set of functional descriptors for each window instance.
    
    Args:
        data: Numpy array of shape (n_windows, window_size, features_per_sensor)
        raw_labels: Numpy array of shape (n_windows,)
        
    Returns:
        tuple: (functionals, raw_labels) where functionals is a Numpy array of shape (n_windows, num_descriptors)
    """
    # Compute statistical descriptors along the time axis (axis=1) for all windows simultaneously
    mean_vals = np.mean(data, axis=1)
    std_vals = np.std(data, axis=1)
    var_vals = np.var(data, axis=1)
    min_vals = np.min(data, axis=1)
    max_vals = np.max(data, axis=1)
    median_vals = np.median(data, axis=1)
    
    # Stack the computed features horizontally
    # Resulting shape: (n_windows, features_per_sensor * 6)
    functionals = np.hstack((mean_vals, std_vals, var_vals, min_vals, max_vals, median_vals))
    
    return functionals, raw_labels

def load_dataset(base_paths, sensors_list, valid_labels, window_size, features_per_sensor):
    """
    Loads the TFM dataset from the specified base paths.
    Args:
        base_paths: List of base paths to load the dataset from.
        sensors_list: List of sensors to load.
        labels_list: List of labels to load.
    Returns:
        A tuple containing:
            X: Numpy array of shape (n_samples, WINDOW_SIZE, N_CHANNELS) with the sensor data.
            y: Numpy array of shape (n_samples,) with the labels.
            subject_ids: Numpy array of shape (n_samples,) with the subject IDs.
    """ 
    X_list, y_list, subject_ids = [], [], []
    # Iterate through each provided base path
    for path in base_paths:
        print(f"\t[Loading dataset from {path}]")
        # Identify all subject directories (assuming they start with 'P')
        subjects = sorted([d for d in os.listdir(path) if d.startswith('P')], key=lambda x: int(x[1:]))
        for sub_idx, subject in enumerate(subjects):
            print(f"\t\t[Processing subject: {subject}]")
            sub_path = os.path.join(path, subject)
            # Identify all session directories for the current subject
            sessions = sorted([d for d in os.listdir(sub_path) if os.path.isdir(os.path.join(sub_path, d))])
            for session in sessions:
                print(f"\t\t\t[Processing session: {session}]")
                sess_path = os.path.join(sub_path, session)
                session_sensors, session_labels, valid_session = [], None, True
                # Process data for each specified sensor
                for sensor in sensors_list:
                    file_path = os.path.join(sess_path, f'sensor_{sensor}.csv')
                    
                    data, raw_labels = load_sensor_data(file_path, window_size, features_per_sensor)
                    #print("data: ", data)
                    #print("raw_labels: ", raw_labels)
                    if data is None:
                        valid_session = False
                        print(f"\t\t\t[Warning: Skipped session {session} for subject {subject} due to invalid or missing sensor data]")
                        break
                        
                    labels_corrected, indices_to_keep = [], []
                    # Iterate through rows to validate and correct labels
                    for idx, label in enumerate(raw_labels):
                        corrected = validate_and_correct_label(label, valid_labels)
                        if corrected: 
                            labels_corrected.append(corrected); 
                            indices_to_keep.append(idx)
                        else:
                            print(f"\t\t\t[Warning: Skipped label {label} for session {session} for subject {subject} due to invalid or missing label]")
                    
                    # Keep only data for valid labels
                    data = data[indices_to_keep]
                    labels = np.array(labels_corrected)

                    session_sensors.append(data)
                    
                    # Store session labels (assuming they are identical across all sensors in a session)
                    if session_labels is None:
                        session_labels = labels

                # Only include data if all sensors were successfully processed for the session
                if valid_session and len(session_sensors) == len(sensors_list):
                    # Find the minimum number of windows across all sensors to handle length mismatches
                    min_w = min(s.shape[0] for s in session_sensors)
                    # Concatenate data from all sensors along the last axis
                    X_list.append(np.concatenate([s[:min_w] for s in session_sensors], axis=2))
                    y_list.append(session_labels[:min_w])
                    # Create an array tracking the subject ID for each window
                    subject_ids.append(np.full(min_w, sub_idx))
                else:
                    print(f"\t\t\t[Warning: Skipped session {session} due to invalid or missing sensor data]")
    
    # Concatenate the arrays for the entire dataset
    final_X = np.concatenate(X_list) if X_list else np.array([])
    final_y = np.concatenate(y_list) if y_list else np.array([])
    final_subject_ids = np.concatenate(subject_ids) if subject_ids else np.array([])
    
    print(f"\n\t[Finished loading dataset]")
    print(f"\t[Result] Total windows loaded: {final_X.shape[0] if final_X.size > 0 else 0}")
    print(f"\t[Result] X shape: {final_X.shape}, y shape: {final_y.shape}")
    
    return final_X, final_y, final_subject_ids

def plot_temporal_evolution(data, labels, window_size, features_per_sensor, axis_names=None, sampling_rate=50):
    """
    Generates a graphical representation of the temporal evolution of sensor values.
    Plots one window per unique label in separate subplots.
    
    Args:
        data: Numpy array of shape (n_samples, window_size, features_per_sensor) containing sensor data.
        labels: Numpy array of shape (n_samples,) containing the labels for each window.
        window_size: Number of samples per window.
        features_per_sensor: Number of features (axes) per sensor.
        axis_names: Optional list of names for the axes (e.g., ['X', 'Y', 'Z']).
        sampling_rate: The sampling rate of the sensor in Hz (default: 50).
    """
    unique_labels = np.unique(labels)
    n_labels = len(unique_labels)
    
    if n_labels == 0:
        print("No labels found to plot.")
        return
        
    fig, axes = plt.subplots(n_labels, 1, figsize=(15, 4 * n_labels), sharex=True)
    if n_labels == 1:
        axes = [axes]
        
    # Create a time array in seconds for a single window
    time_sec = np.arange(window_size) / sampling_rate
    
    for i, label in enumerate(unique_labels):
        # Find the first window with this label
        idx = np.where(labels == label)[0][0]
        sample = data[idx] # Shape: (window_size, features_per_sensor)
        
        ax = axes[i]
        for f in range(features_per_sensor):
            axis_label = axis_names[f] if axis_names and f < len(axis_names) else f'Axis {f}'
            ax.plot(time_sec, sample[:, f], label=axis_label, alpha=0.7)
            
        ax.set_ylabel("Sensor Value")
        ax.legend()
        ax.set_title(f"Label: {label}") 
        
    axes[-1].set_xlabel("Time (seconds)")
    plt.tight_layout()
    plt.show()