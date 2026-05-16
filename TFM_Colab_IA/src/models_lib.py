import json
import numpy as np
import tensorflow as tf
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import Input, LSTM, Dense, Dropout, BatchNormalization, Bidirectional
from tensorflow.keras.callbacks import EarlyStopping, ReduceLROnPlateau

import matplotlib.pyplot as plt
import seaborn as sns

from sklearn.preprocessing import LabelEncoder, StandardScaler
from sklearn.metrics import confusion_matrix, accuracy_score, classification_report
from sklearn.naive_bayes import GaussianNB
from sklearn.linear_model import LogisticRegression
from sklearn.tree import DecisionTreeClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.svm import SVC
from sklearn.dummy import DummyClassifier
from tensorflow.keras.regularizers import l2

def create_bilstm_model(num_time_steps=200, num_features_per_step=12, num_output_classes=2):
    """
    Creates and compiles an improved Bidirectional LSTM neural network for sequence classification.
    
    The model architecture consists of:
    - Input layer matching the time window and sensor channels.
    - Two Bidirectional LSTM layers to capture temporal dependencies from both past and future.
    - Batch Normalization and Dropout for regularization and stable training.
    - Fully connected Dense layers for final classification.

    Args:
        num_time_steps: number of time steps in the input sequences.
        num_features_per_step: number of features per time step (channels).
        num_output_classes: number of output nodes in the classification model.
    Returns:
        model: A compiled tf.keras.Sequential model.
    """
    model = Sequential([
        # 1. Input Layer: Defines the expected shape of incoming data.
        # WINDOW_SIZE is the number of time steps, N_CHANNELS is the number of features per step.
        Input(shape=(num_time_steps, num_features_per_step)),

        # 2. First Bidirectional LSTM Layer
        # Bidirectional wrapper allows the LSTM to process the sequence forwards and backwards, 
        # extracting richer context from both past and future states of the signal.
        # return_sequences=True means it passes the full sequence of outputs to the next layer.
        Bidirectional(LSTM(32, return_sequences=True, kernel_regularizer=l2(0.001))),
        
        # 3. Batch Normalization: Standardizes the activations from the previous layer,
        # which helps to accelerate training and makes the network more stable.
        BatchNormalization(),
        
        # 4. Dropout: Randomly sets 50% of the input units to 0 at each update during training,
        # which helps prevent the model from overfitting to the training data.
        Dropout(0.5),

        # 5. Second Bidirectional LSTM Layer
        # Compresses the sequence into a single output vector (since return_sequences=False by default)
        Bidirectional(LSTM(16, kernel_regularizer=l2(0.001))),
        
        # 6. Another Dropout layer for further regularization
        Dropout(0.5),

        # 7. Dense (Fully Connected) Layer: Learns non-linear combinations of the extracted LSTM features.
        Dense(8, activation='relu', kernel_regularizer=l2(0.01)),
        
        # 8. Output Layer: Maps the output to the number of possible classes.
        # 'softmax' activation converts the raw outputs into a probability distribution 
        # (all output values sum to 1.0).
        Dense(num_output_classes, activation='softmax')
    ])
    
    # 9. Model Compilation
    # - optimizer='adam': Adaptive learning rate optimization algorithm.
    # - loss='sparse_categorical_crossentropy': Ideal for multi-class classification where labels are integers.
    # - metrics=['accuracy']: We want to track classification accuracy during training.
    model.compile(optimizer='adam', loss='sparse_categorical_crossentropy', metrics=['accuracy'])
    
    return model

def run_experiment(X, y, classes=['Yes', 'No'], subjects=np.arange(20), title='Experiment', config={}):
    # Default configuration
    default_config = {
        "general": {
            "verbose": 1,
            "window_size": 200,
            "num_features_per_step": 12,
            "StandardScaler": False
        },
        "training": {
            "epochs": 100,
            "batch_size": 64,
            "validation_split": 0.1,
        },
        "early_stopping": {
            "monitor": "val_loss",
            "patience": 12,
            "start_from_epoch": 15
        },
        "reduce_lr": {
            "monitor": "val_loss",
            "factor": 0.5,
            "patience": 5,
            "min_lr": 0.0001
        }
    }
    # Actualizar la configuración con la del usuario
    default_config.update(config)
    config = default_config

    # Print Configuration: given that it is a JSON, we print it in a readable format
    print("Configuration: ", json.dumps(config, indent=4))
    
    print(f"\n{'='*20} EXPERIMENT: {title} {'='*20}")
    le = LabelEncoder().fit(classes)
    y_enc = le.transform(y)
    unique_subs = np.unique(subjects)
    all_y_true, all_y_pred, fold_accs = [], [], []

    # Extraer las configuraciones
    gen_cfg = config["general"]
    train_cfg = config["training"]
    es_cfg = config["early_stopping"]
    lr_cfg = config["reduce_lr"]

    # Parada temprana obligando a un mínimo de épocas.
    early_stop = EarlyStopping(
        monitor=es_cfg.get('monitor', 'val_loss'), 
        patience=es_cfg.get('patience', 12), 
        restore_best_weights=True, 
        start_from_epoch=es_cfg.get('start_from_epoch', 15)
    )

    # Reducción de la tasa de aprendizaje si no hay mejora
    reduce_lr = ReduceLROnPlateau(
        monitor=lr_cfg.get('monitor', 'val_loss'), 
        factor=lr_cfg.get('factor', 0.5), 
        patience=lr_cfg.get('patience', 5), 
        min_lr=lr_cfg.get('min_lr', 0.0001), 
        verbose=0
    )

    for test_sub in unique_subs:
        X_train, y_train = X[subjects != test_sub], y_enc[subjects != test_sub]
        X_test, y_test = X[subjects == test_sub], y_enc[subjects == test_sub]

        #if gen_cfg["StandardScaler"]:
        #    scaler = StandardScaler()
        #    X_train = scaler.fit_transform(X_train.reshape(-1, X_train.shape[2])).reshape(X_train.shape)
        #    X_test = scaler.transform(X_test.reshape(-1, X_test.shape[2])).reshape(X_test.shape)

        model = create_bilstm_model(num_time_steps=gen_cfg["window_size"], 
                                    num_features_per_step=gen_cfg["num_features_per_step"], 
                                    num_output_classes=len(classes))

        history = model.fit(
            X_train, y_train, 
            epochs=train_cfg.get('epochs', 100), 
            batch_size=train_cfg.get('batch_size', 64), 
            verbose=gen_cfg.get('verbose', 0), 
            validation_split=train_cfg.get('validation_split', 0.1), 
            callbacks=[early_stop, reduce_lr]
        )

        preds = np.argmax(model.predict(X_test, verbose=gen_cfg.get('verbose', 0)), axis=1)
        acc = accuracy_score(y_test, preds)
        fold_accs.append(acc)

        epocas_reales = len(history.history['loss'])
        print(f"Fold P{test_sub+1}: {acc:.4f} (Épocas ejecutadas: {epocas_reales}/{train_cfg.get('epochs', 100)})")

        all_y_true.extend(y_test); all_y_pred.extend(preds)

    mean_acc = np.mean(fold_accs)
    std_acc = np.std(fold_accs)
    ci95 = 1.96 * (std_acc / np.sqrt(len(fold_accs)))
    print(f"\n[GLOBAL RESULT] Media: {mean_acc:.4f} ± {ci95:.4f} (95% CI)")
    cm = confusion_matrix(all_y_true, all_y_pred)
    plt.figure(figsize=(8, 6))
    sns.heatmap(cm, annot=True, fmt='d', cmap='Blues', xticklabels=le.classes_, yticklabels=le.classes_)
    plt.title(f'Confusion Matrix: {title}')
    plt.show()
    print(classification_report(all_y_true, all_y_pred, target_names=le.classes_))

def run_baseline_experiment(X, y, classes=['Yes', 'No'], subjects=np.arange(20), title='Baseline Experiment', config={}):
    default_config = {
        "ZeroR": {
            "enabled": True
        },
        "Naive Bayes": {
            "enabled": True
        },
        "Logistic Regression": {
            "enabled": True,
            "max_iter": 1000,
            "C": 1.0
        },
        "Decision Tree": {
            "enabled": True,
            "max_depth": None
        },
        "Random Forest": {
            "enabled": True,
            "n_estimators": 100,
            "n_jobs": -1
        },
        "SVM": {
            "enabled": True,
            "C": 1.0,
            "kernel": 'rbf'
        }
    }
    
    # Update default config with user config
    for clf_name, clf_cfg in config.items():
        if clf_name in default_config:
            default_config[clf_name].update(clf_cfg)
    config = default_config
    
    print("Configuration: ", json.dumps(config, indent=4))
    
    print(f"\n{'='*20} BASELINE EXPERIMENT: {title} {'='*20}")
    le = LabelEncoder().fit(classes)
    y_enc = le.transform(y)
    unique_subs = np.unique(subjects)
    
    classifiers = {}
    if config["ZeroR"]["enabled"]:
        classifiers["ZeroR"] = DummyClassifier(strategy='most_frequent')
        
    if config["Naive Bayes"]["enabled"]:
        classifiers["Naive Bayes"] = GaussianNB()
        
    if config["Logistic Regression"]["enabled"]:
        classifiers["Logistic Regression"] = LogisticRegression(
            max_iter=config["Logistic Regression"]["max_iter"],
            C=config["Logistic Regression"]["C"]
        )
        
    if config["Decision Tree"]["enabled"]:
        classifiers["Decision Tree"] = DecisionTreeClassifier(
            max_depth=config["Decision Tree"]["max_depth"]
        )
        
    if config["Random Forest"]["enabled"]:
        classifiers["Random Forest"] = RandomForestClassifier(
            n_estimators=config["Random Forest"]["n_estimators"],
            n_jobs=config["Random Forest"]["n_jobs"]
        )
        
    if config["SVM"]["enabled"]:
        classifiers["SVM"] = SVC(
            C=config["SVM"]["C"],
            kernel=config["SVM"]["kernel"],
            probability=False
        )
    
    results = {}
    
    for name, clf in classifiers.items():
        print(f"\n--- Training {name} ---")
        all_y_true, all_y_pred, fold_accs = [], [], []
        
        for test_sub in unique_subs:
            X_train, y_train = X[subjects != test_sub], y_enc[subjects != test_sub]
            X_test, y_test = X[subjects == test_sub], y_enc[subjects == test_sub]
            
            # Standardize features (important for LR, SVM)
            scaler = StandardScaler()
            X_train_scaled = scaler.fit_transform(X_train)
            X_test_scaled = scaler.transform(X_test)
            
            clf.fit(X_train_scaled, y_train)
            preds = clf.predict(X_test_scaled)
            
            acc = accuracy_score(y_test, preds)
            fold_accs.append(acc)
            
            all_y_true.extend(y_test)
            all_y_pred.extend(preds)
            
            print(f"Fold P{test_sub+1}: {acc:.4f}")
            
        mean_acc = np.mean(fold_accs)
        std_acc = np.std(fold_accs)
        # Calculate 95% Confidence Interval for the mean across folds
        ci95 = 1.96 * (std_acc / np.sqrt(len(fold_accs)))
        
        results[name] = {
            "mean_acc": mean_acc,
            "std_acc": std_acc,
            "ci95": ci95,
            "fold_accs": fold_accs,
            "y_true": all_y_true,
            "y_pred": all_y_pred
        }
        print(f"[{name}] GLOBAL RESULT Media: {mean_acc:.4f} ± {ci95:.4f} (95% CI)")
        
    print(f"\n{'='*20} SUMMARY OF BASELINE CLASSIFIERS {'='*20}")
    for name, res in results.items():
        print(f"{name:<20}: {res['mean_acc']:.4f} ± {res['ci95']:.4f} (95% CI)")
        
    # Plot confusion matrices
    num_clfs = len(classifiers)
    fig, axes = plt.subplots(1, num_clfs, figsize=(5 * num_clfs, 5))
    if num_clfs == 1:
        axes = [axes]
        
    for ax, (name, res) in zip(axes, results.items()):
        cm = confusion_matrix(res['y_true'], res['y_pred'])
        sns.heatmap(cm, annot=True, fmt='d', cmap='Blues', xticklabels=le.classes_, yticklabels=le.classes_, ax=ax)
        ax.set_title(f'{name}\nAcc: {res["mean_acc"]:.4f}')
        ax.set_ylabel('True Label')
        ax.set_xlabel('Predicted Label')
        
    plt.tight_layout()
    plt.show()
    
    for name, res in results.items():
        print(f"\n--- Classification Report: {name} ---")
        print(classification_report(res['y_true'], res['y_pred'], target_names=le.classes_))

def run_experiment_dual_test(X_c, y_c, sub_c, X_com, y_com, sub_com, classes=['Yes', 'No'], title='Dual Test Experiment', config={}):
    # 1. Cargar configuración por defecto y actualizar con la del usuario
    default_config = {
        "general": {"verbose": 1, "window_size": 200, "num_features_per_step": 12, "StandardScaler": False},
        "training": {"epochs": 100, "batch_size": 64, "validation_split": 0.1},
        "early_stopping": {"monitor": "val_loss", "patience": 12, "start_from_epoch": 15},
        "reduce_lr": {"monitor": "val_loss", "factor": 0.5, "patience": 5, "min_lr": 0.0001}
    }
    default_config.update(config)
    config = default_config
    
    gen_cfg = config["general"]
    train_cfg = config["training"]
    es_cfg = config["early_stopping"]
    lr_cfg = config["reduce_lr"]

    print("Configuration: ", json.dumps(config, indent=4))
    print(f"\n{'='*20} DUAL EXPERIMENT: {title} {'='*20}")
    
    # 2. Codificar etiquetas
    le = LabelEncoder().fit(classes)
    y_c_enc = le.transform(y_c)
    y_com_enc = le.transform(y_com)
    
    # 3. Identificar sujetos únicos (asumiendo que están en ambos datasets o en uno de ellos)
    unique_subs = np.unique(np.concatenate([sub_c, sub_com]))
    
    fold_accs_c, fold_accs_com = [], []

    # Callbacks
    early_stop = EarlyStopping(monitor=es_cfg.get('monitor', 'val_loss'), patience=es_cfg.get('patience', 12), restore_best_weights=True, start_from_epoch=es_cfg.get('start_from_epoch', 15))
    reduce_lr = ReduceLROnPlateau(monitor=lr_cfg.get('monitor', 'val_loss'), factor=lr_cfg.get('factor', 0.5), patience=lr_cfg.get('patience', 5), min_lr=lr_cfg.get('min_lr', 0.0001), verbose=0)

    # 4. Bucle LOSO
    for test_sub in unique_subs:
        # --- PREPARAR ENTRENAMIENTO (Combinado) ---
        X_train_c = X_c[sub_c != test_sub]
        y_train_c = y_c_enc[sub_c != test_sub]
        
        X_train_com = X_com[sub_com != test_sub]
        y_train_com = y_com_enc[sub_com != test_sub]
        
        X_train = np.concatenate([X_train_c, X_train_com]) if len(X_train_c) > 0 and len(X_train_com) > 0 else X_train_c if len(X_train_c) > 0 else X_train_com
        y_train = np.concatenate([y_train_c, y_train_com]) if len(y_train_c) > 0 and len(y_train_com) > 0 else y_train_c if len(y_train_c) > 0 else y_train_com

        # --- PREPARAR TEST (Separado) ---
        X_test_c = X_c[sub_c == test_sub]
        y_test_c = y_c_enc[sub_c == test_sub]
        
        X_test_com = X_com[sub_com == test_sub]
        y_test_com = y_com_enc[sub_com == test_sub]

        # --- ESCALADO ---
        #if gen_cfg["StandardScaler"]:
        #    scaler = StandardScaler()
        #    X_train = scaler.fit_transform(X_train.reshape(-1, X_train.shape[2])).reshape(X_train.shape)
        #    if len(X_test_c) > 0: X_test_c = scaler.transform(X_test_c.reshape(-1, X_test_c.shape[2])).reshape(X_test_c.shape)
        #    if len(X_test_com) > 0: X_test_com = scaler.transform(X_test_com.reshape(-1, X_test_com.shape[2])).reshape(X_test_com.shape)

        # --- MODELO ---
        model = create_bilstm_model(num_time_steps=gen_cfg["window_size"], num_features_per_step=gen_cfg["num_features_per_step"], num_output_classes=len(classes))
        
        history = model.fit(X_train, y_train, epochs=train_cfg.get('epochs', 100), batch_size=train_cfg.get('batch_size', 64), verbose=gen_cfg.get('verbose', 0), validation_split=train_cfg.get('validation_split', 0.1), callbacks=[early_stop, reduce_lr])

        # --- EVALUACIÓN CUSTOM ---
        if len(X_test_c) > 0:
            preds_c = np.argmax(model.predict(X_test_c, verbose=gen_cfg.get('verbose', 0)), axis=1)
            acc_c = accuracy_score(y_test_c, preds_c)
            fold_accs_c.append(acc_c)
        else:
            acc_c = np.nan # Manejo de error por si un sujeto no tiene datos en este corpus

        # --- EVALUACIÓN COMERCIAL ---
        if len(X_test_com) > 0:
            preds_com = np.argmax(model.predict(X_test_com, verbose=gen_cfg.get('verbose', 0)), axis=1)
            acc_com = accuracy_score(y_test_com, preds_com)
            fold_accs_com.append(acc_com)
        else:
            acc_com = np.nan
            
        epocas_reales = len(history.history['loss'])
        print(f"Fold P{test_sub+1} (Epochs: {epocas_reales}) | Acc Custom: {acc_c:.4f} | Acc Commercial: {acc_com:.4f}")

    # 5. Resultados Globales
    print(f"\n{'-'*20} GLOBAL RESULTS {'-'*20}")
    
    valid_accs_c = [a for a in fold_accs_c if not np.isnan(a)]
    mean_c = np.mean(valid_accs_c)
    ci95_c = 1.96 * (np.std(valid_accs_c) / np.sqrt(len(valid_accs_c)))
    print(f"CUSTOM TEST     -> Media: {mean_c:.4f} ± {ci95_c:.4f} (95% CI)")

    valid_accs_com = [a for a in fold_accs_com if not np.isnan(a)]
    mean_com = np.mean(valid_accs_com)
    ci95_com = 1.96 * (np.std(valid_accs_com) / np.sqrt(len(valid_accs_com)))
    print(f"COMMERCIAL TEST -> Media: {mean_com:.4f} ± {ci95_com:.4f} (95% CI)")
