import dash
from dash import dcc, html, Input, Output, callback
import plotly.graph_objs as go
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import os

# Initialize the Dash app
app = dash.Dash(__name__)
server = app.server

# Sample data generation
np.random.seed(42)
dates = pd.date_range(start='2024-01-01', periods=365, freq='D')
data = {
    'Date': dates,
    'Calls': np.random.randint(50, 200, 365),
    'Duration': np.random.randint(5, 60, 365),
    'Satisfaction': np.random.uniform(3, 5, 365).round(2),
}
df = pd.DataFrame(data)

# Define the app layout
app.layout = html.Div([
    html.Div([
        html.H1("Call Center Dashboard", style={'textAlign': 'center', 'marginBottom': '30px'}),
        html.Div([
            html.Div([
                html.Label("Select Date Range:"),
                dcc.DatePickerRange(
                    id='date-picker-range',
                    start_date=dates[0],
                    end_date=dates[-1],
                    display_format='YYYY-MM-DD',
                    style={'width': '100%'}
                ),
            ], style={'marginBottom': '20px'}),
            html.Div([
                html.Label("Select Metric:"),
                dcc.Dropdown(
                    id='metric-dropdown',
                    options=[
                        {'label': 'Calls', 'value': 'Calls'},
                        {'label': 'Duration', 'value': 'Duration'},
                        {'label': 'Satisfaction', 'value': 'Satisfaction'},
                    ],
                    value='Calls',
                    style={'width': '100%'}
                ),
            ], style={'marginBottom': '20px'}),
        ], style={'display': 'flex', 'gap': '20px', 'marginBottom': '20px'}),
    ], style={'padding': '20px', 'backgroundColor': '#f8f9fa', 'borderRadius': '8px', 'marginBottom': '20px'}),

    # Graphs
    html.Div([
        html.Div([
            dcc.Graph(id='time-series-chart'),
        ], style={'width': '48%', 'display': 'inline-block'}),
        html.Div([
            dcc.Graph(id='distribution-chart'),
        ], style={'width': '48%', 'display': 'inline-block', 'float': 'right'}),
    ]),

    # Key Metrics
    html.Div([
        html.Div(id='metrics-container', style={'display': 'flex', 'gap': '20px', 'flexWrap': 'wrap', 'marginTop': '30px'}),
    ]),
])

# Callback to update charts and metrics
@callback(
    [Output('time-series-chart', 'figure'),
     Output('distribution-chart', 'figure'),
     Output('metrics-container', 'children')],
    [Input('date-picker-range', 'start_date'),
     Input('date-picker-range', 'end_date'),
     Input('metric-dropdown', 'value')]
)
def update_charts(start_date, end_date, metric):
    # Filter data based on date range
    filtered_df = df[(df['Date'] >= start_date) & (df['Date'] <= end_date)]

    # Time series chart
    time_series = go.Figure(data=[
        go.Scatter(
            x=filtered_df['Date'],
            y=filtered_df[metric],
            mode='lines+markers',
            name=metric,
            line=dict(color='#1f77b4', width=2),
            marker=dict(size=4),
        )
    ])
    time_series.update_layout(
        title=f'{metric} Over Time',
        xaxis_title='Date',
        yaxis_title=metric,
        hovermode='x unified',
        template='plotly_white',
    )

    # Distribution chart
    distribution = go.Figure(data=[
        go.Histogram(
            x=filtered_df[metric],
            nbinsx=30,
            name=metric,
            marker=dict(color='#ff7f0e'),
        )
    ])
    distribution.update_layout(
        title=f'{metric} Distribution',
        xaxis_title=metric,
        yaxis_title='Frequency',
        template='plotly_white',
    )

    # Calculate metrics
    total_calls = filtered_df['Calls'].sum()
    avg_duration = filtered_df['Duration'].mean()
    avg_satisfaction = filtered_df['Satisfaction'].mean()
    
    # Calculate growth rate (percentage change from first to last value)
    if len(filtered_df) > 1:
        first_value = filtered_df[metric].iloc[0]
        last_value = filtered_df[metric].iloc[-1]
        if first_value != 0:
            growth_rate = (last_value - first_value) / first_value
        else:
            growth_rate = 0
    else:
        growth_rate = 0

    # Key metrics cards
    metrics_cards = [
        html.Div([
            html.H3("Total Calls"),
            html.P(f"{total_calls:,.0f}", style={'fontSize': '24px', 'fontWeight': 'bold'}),
        ], style={'flex': '1', 'padding': '20px', 'backgroundColor': '#e3f2fd', 'borderRadius': '8px'}),
        html.Div([
            html.H3("Avg Duration (min)"),
            html.P(f"{avg_duration:.1f}", style={'fontSize': '24px', 'fontWeight': 'bold'}),
        ], style={'flex': '1', 'padding': '20px', 'backgroundColor': '#f3e5f5', 'borderRadius': '8px'}),
        html.Div([
            html.H3("Avg Satisfaction"),
            html.P(f"{avg_satisfaction:.2f}", style={'fontSize': '24px', 'fontWeight': 'bold'}),
        ], style={'flex': '1', 'padding': '20px', 'backgroundColor': '#e8f5e9', 'borderRadius': '8px'}),
        html.Div([
            html.H3("Growth Rate"),
            html.P(f"{growth_rate:.1%}", style={'fontSize': '24px', 'fontWeight': 'bold'}),
        ], style={'flex': '1', 'padding': '20px', 'backgroundColor': '#fff3e0', 'borderRadius': '8px'}),
    ]

    return time_series, distribution, metrics_cards


if __name__ == '__main__':
    app.run_server(debug=True)
