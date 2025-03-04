import random
import streamlit as st
import pandas as pd
import base64
from io import BytesIO

st.set_page_config(page_title="Grant Hour Allocation Tool", layout="wide")

# Define the list of available grants in the specified order
# Flipped REA #3 Lincoln and REA #3 Omaha as requested
AVAILABLE_GRANTS = [
    "FY 24 Matching Grant",
    "ASA #3",
    "ASA #4",
    "REA #1",
    "REA #2",
    "PC Housing HAF Omaha",
    "PC Housing HAF Lincoln",
    "FY 25 RSS Grant",
    "UHP #1",
    "UHP #4",
    "UHP #5",
    "REA #3 Omaha",
    "REA #3 Lincoln",
    "Non-Grant"
]

def allocate_hours(grants_data):
    # Convert dataframe to list of tuples and normalize to exact 0.25 hour increments
    grants_list = []
    total_original = 0
    
    for _, row in grants_data.iterrows():
        name = row["Grant Name"]
        # Round to nearest 0.25 to avoid floating point issues
        original_hours = row["Maximum Hours"]
        max_hours = round(original_hours * 4) / 4
        grants_list.append((name, max_hours, original_hours))
        total_original += original_hours
    
    # Adjust for any rounding discrepancies to ensure exactly 80 hours
    total_after_rounding = sum(max_hours for _, max_hours, _ in grants_list)
    
    # If we're close to 80 hours but not exactly due to rounding,
    # adjust the largest grant to make the total exactly 80
    if abs(total_original - 80.0) < 0.1 and abs(total_after_rounding - 80.0) > 0.01:
        # Find the largest grant
        largest_idx = max(range(len(grants_list)), key=lambda i: grants_list[i][1])
        name, hours, original = grants_list[largest_idx]
        
        # Adjust it to make the total exactly 80
        adjusted_hours = hours + (80.0 - total_after_rounding)
        # Still ensure it's in 0.25 increments
        adjusted_hours = round(adjusted_hours * 4) / 4
        
        # Replace with adjusted value
        grants_list[largest_idx] = (name, adjusted_hours, original)
    
    # Convert to the expected format for the algorithm
    grants = [(name, hours) for name, hours, _ in grants_list]
    
    # Define workdays
    workdays = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
    
    # Create a 2-week schedule structure
    schedule = {
        1: {day: [0.0 for _ in grants] for day in workdays},
        2: {day: [0.0 for _ in grants] for day in workdays}
    }
    
    # Get total hours for each day (8 hours)
    day_total_target = 8.0
    
    # Track daily allocated hours
    day_allocated = {week: {day: 0.0 for day in workdays} for week in [1, 2]}
    
    # Track allocated hours for each grant
    grant_allocated = [0.0 for _ in grants]
    
    # Calculate total available hours across all grants after adjustments
    total_available_hours = sum(max_hours for _, max_hours in grants)
    
    # Create a list of all days
    all_days = [(week, day) for week in [1, 2] for day in workdays]
    
    # Check if we have exactly 80 hours (should be exact now)
    is_80_hour_case = abs(total_available_hours - 80.0) < 0.01
    
    if is_80_hour_case:
        # First, let's fill each day exactly to 8 hours
        
        # Shuffle days to randomize allocation
        random.shuffle(all_days)
        
        # Approach: Fill all days to exactly 8 hours using a greedy algorithm
        
        # Sort grants by size (largest first) to prioritize allocation
        sorted_grants = sorted(enumerate(grants), key=lambda x: x[1][1], reverse=True)
        
        # Track remaining hours for each grant
        remaining_hours = [hours for _, hours in grants]
        
        # Step 1: Try to fill each day with larger chunks first
        for week, day in all_days:
            # Reset day's allocated hours
            day_allocated[week][day] = 0
            for i in range(len(grants)):
                schedule[week][day][i] = 0
            
            # Available hours for this day
            available = 8.0
            
            # Try to allocate larger chunks first
            possible_chunks = [8.0, 4.0, 2.0, 1.5, 1.0, 0.75, 0.5, 0.25]
            
            # Randomize the order of grants for this day
            day_grants = list(sorted_grants)
            random.shuffle(day_grants)
            
            # Try each chunk size
            for chunk in possible_chunks:
                if chunk > available or chunk < 0.25:
                    continue
                
                # Try to find grants that can use this chunk size
                for idx, (i, (name, _)) in enumerate(day_grants):
                    if remaining_hours[i] >= chunk:
                        # Allocate this chunk
                        schedule[week][day][i] += chunk
                        day_allocated[week][day] += chunk
                        remaining_hours[i] -= chunk
                        available -= chunk
                        
                        # If this grant is now fully allocated, remove it
                        if remaining_hours[i] < 0.25:
                            day_grants.pop(idx)
                        
                        # If the day is full, break
                        if available < 0.25:
                            break
                        
                        # If more of this chunk can be allocated, try again
                        if available >= chunk:
                            continue
                
                # If the day is full, break
                if available < 0.25:
                    break
            
            # If we still have space, fill with remaining hours
            if available >= 0.25:
                # Use any grant with remaining hours
                for idx, (i, (name, _)) in enumerate(day_grants):
                    if remaining_hours[i] >= 0.25:
                        # Calculate how much to allocate
                        allocation = min(remaining_hours[i], available)
                        allocation = round(allocation * 4) / 4  # Round to nearest 0.25
                        
                        if allocation >= 0.25:
                            schedule[week][day][i] += allocation
                            day_allocated[week][day] += allocation
                            remaining_hours[i] -= allocation
                            available -= allocation
                        
                        # If this grant is now fully allocated, remove it
                        if remaining_hours[i] < 0.25:
                            day_grants.pop(idx)
                        
                        # If the day is full, break
                        if available < 0.25:
                            break
        
        # Step 2: After initial allocation, verify and adjust
        # Calculate actual allocated hours
        for i in range(len(grants)):
            grant_allocated[i] = sum(schedule[week][day][i] for week in [1, 2] for day in workdays)
        
        # Check if any grants are under-allocated
        for i, (name, max_hours) in enumerate(grants):
            if abs(grant_allocated[i] - max_hours) > 0.01:
                # Find how much is still needed
                needed = max_hours - grant_allocated[i]
                
                if needed > 0:
                    # Find days that can accommodate more hours
                    for week in [1, 2]:
                        for day in workdays:
                            # Check if this day has room
                            day_total = sum(schedule[week][day])
                            if day_total < 8.0 - 0.01:
                                # Calculate how much to add
                                available = 8.0 - day_total
                                allocation = min(needed, available)
                                allocation = round(allocation * 4) / 4  # Round to nearest 0.25
                                
                                if allocation >= 0.25:
                                    schedule[week][day][i] += allocation
                                    grant_allocated[i] += allocation
                                    needed -= allocation
                                
                                # If we've allocated all needed hours, break
                                if needed < 0.01:
                                    break
                        
                        # If we've allocated all needed hours, break
                        if needed < 0.01:
                            break
                
                elif needed < 0:
                    # We've over-allocated - reduce allocation
                    excess = -needed
                    
                    for week in [1, 2]:
                        for day in workdays:
                            if schedule[week][day][i] > 0:
                                reduction = min(excess, schedule[week][day][i])
                                reduction = round(reduction * 4) / 4  # Round to nearest 0.25
                                
                                schedule[week][day][i] -= reduction
                                grant_allocated[i] -= reduction
                                excess -= reduction
                                
                                # If we've fixed the excess, break
                                if excess < 0.01:
                                    break
                        
                        # If we've fixed the excess, break
                        if excess < 0.01:
                            break
        
        # Step 3: Final check - ensure each day has exactly 8 hours
        for week in [1, 2]:
            for day in workdays:
                day_total = sum(schedule[week][day])
                
                # If day is not exactly 8 hours (considering precision issues)
                if abs(day_total - 8.0) > 0.01:
                    # Adjust by adding or removing hours
                    if day_total < 8.0:  # Need to add hours
                        shortage = 8.0 - day_total
                        # Try to find a grant with remaining hours
                        for i, (name, max_hours) in enumerate(grants):
                            if grant_allocated[i] < max_hours - 0.01:
                                to_add = min(shortage, max_hours - grant_allocated[i])
                                to_add = round(to_add * 4) / 4  # Round to nearest 0.25
                                
                                if to_add >= 0.25:
                                    schedule[week][day][i] += to_add
                                    grant_allocated[i] += to_add
                                    shortage -= to_add
                                
                                if shortage < 0.01:
                                    break
                    else:  # Need to remove hours
                        excess = day_total - 8.0
                        # Find a grant with hours allocated on this day
                        for i in range(len(grants)):
                            if schedule[week][day][i] > 0:
                                to_remove = min(excess, schedule[week][day][i])
                                to_remove = round(to_remove * 4) / 4  # Round to nearest 0.25
                                
                                if to_remove >= 0.25:
                                    schedule[week][day][i] -= to_remove
                                    grant_allocated[i] -= to_remove
                                    excess -= to_remove
                                
                                if excess < 0.01:
                                    break
    else:
        # For non-80-hour cases, use a simpler distribution approach
        # Shuffle days for randomization
        random.shuffle(all_days)
        
        # Sort grants from largest to smallest
        sorted_grants = sorted(enumerate(grants), key=lambda x: x[1][1], reverse=True)
        
        # Allocate each grant
        for i, (name, max_hours) in sorted_grants:
            if max_hours <= 0.0:
                continue
                
            remaining = max_hours
            days_to_use = all_days.copy()
            random.shuffle(days_to_use)
            
            # Create varied chunks for more random allocation patterns
            standard_chunks = [4.0, 3.75, 3.5, 3.25, 3.0, 2.75, 2.5, 2.25, 2.0, 1.75, 1.5, 1.25, 1.0, 0.75, 0.5, 0.25]
            # Use a random subset for this particular grant
            num_chunks = random.randint(4, 10)
            varied_chunks = random.sample(standard_chunks, min(num_chunks, len(standard_chunks)))
            varied_chunks.sort(reverse=True)
            
            while remaining > 0.01 and days_to_use:
                week, day = days_to_use.pop(0)
                available = day_total_target - day_allocated[week][day]
                
                if available < 0.25:
                    continue
                
                allocation = None
                # Decide whether to use a standard chunk or a more creative allocation
                if random.random() < 0.7:  # 70% chance to use varied chunks
                    # Find a suitable chunk from our varied set
                    for chunk in varied_chunks:
                        if chunk <= available and chunk <= remaining:
                            allocation = chunk
                            break
                
                # If no allocation yet or we're using creative allocation (30% chance)
                if allocation is None or random.random() < 0.3:
                    # Use a random allocation for more variety
                    max_alloc = min(available, remaining)
                    # Choose a random value between 0.25 and the maximum available
                    allocation = 0.25 + (random.random() * (max_alloc - 0.25))
                    allocation = round(allocation * 4) / 4  # Round to nearest 0.25
                else:
                    allocation = min(remaining, available)
                    # Round to nearest 0.25
                    allocation = round(allocation * 4) / 4
                
                if allocation >= 0.25:
                    schedule[week][day][i] += allocation
                    day_allocated[week][day] += allocation
                    grant_allocated[i] += allocation
                    remaining = max_hours - grant_allocated[i]
    
    # Final verification - make sure we haven't exceeded any grant maximums
    for i, (name, max_hours) in enumerate(grants):
        total = sum(schedule[week][day][i] for week in [1, 2] for day in workdays)
        if total > max_hours + 0.01:
            # This shouldn't happen with the logic above, but just in case
            excess = total - max_hours
            for week in [1, 2]:
                for day in workdays:
                    if schedule[week][day][i] > 0 and excess > 0.01:
                        reduction = min(excess, schedule[week][day][i])
                        schedule[week][day][i] -= reduction
                        day_allocated[week][day] -= reduction
                        excess -= reduction
    
    return schedule, grants

def create_schedule_dataframe(schedule, grants):
    # Create a list to store all records
    records = []
    
    # Process each week, day, and grant
    for week in [1, 2]:
        for day in ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]:
            for i, (name, _) in enumerate(grants):
                if schedule[week][day][i] > 0:
                    records.append({
                        "Week": week,
                        "Day": day,
                        "Grant": name,
                        "Hours": schedule[week][day][i]
                    })
    
    # Convert to DataFrame
    return pd.DataFrame(records)

def create_summary_dataframe(schedule, grants):
    # Create a list to store summary records
    records = []
    
    # Calculate totals for each grant
    for i, (name, max_hrs) in enumerate(grants):
        week1_total = sum(schedule[1][day][i] for day in ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"])
        week2_total = sum(schedule[2][day][i] for day in ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"])
        total = week1_total + week2_total
        
        # Calculate the remaining hours (allowed to be under but not over)
        remaining = max_hrs - total
        
        records.append({
            "Grant": name,
            "Week 1 Hours": week1_total,
            "Week 2 Hours": week2_total,
            "Total Hours": total,
            "Maximum Hours": max_hrs,
            "Remaining Hours": remaining
        })
    
    # Convert to DataFrame
    return pd.DataFrame(records)

def export_to_csv(df):
    """Convert dataframe to CSV format for downloading"""
    return df.to_csv(index=False).encode("utf-8")

def main():
    st.title("Grant Hour Allocation Tool")
    
    st.write("""
    This tool helps you allocate grant hours across a two-week period (Monday-Friday, 8 hours per day).
    When total hours equal 80, each day will be allocated exactly 8 hours.
    """)
    
    # Initialize session state
    if 'grants_data' not in st.session_state:
        st.session_state.grants_data = pd.DataFrame(columns=["Grant Name", "Maximum Hours"])
    
    # Main two-column layout
    col1, col2 = st.columns([1, 1])
    
    with col1:
        st.subheader("Available Grants")
        
        # Filter out already selected grants
        available_grants = [g for g in AVAILABLE_GRANTS if g not in st.session_state.grants_data["Grant Name"].values]
        
        if available_grants:
            # Show the list of available grants
            st.write("Click 'Add' next to a grant to add it to your selection:")
            
            # Create a container for scrollable content if needed
            grants_container = st.container()
            
            # Process each available grant
            for grant in available_grants:
                # Show the grant with an Add button
                col_name, col_btn = grants_container.columns([3, 1])
                col_name.write(grant)
                if col_btn.button("Add", key=f"add_{grant}"):
                    # Add the grant to the selected list with default hours
                    default_hours = 0.0
                    new_data = pd.DataFrame({
                        "Grant Name": [grant], 
                        "Maximum Hours": [default_hours]
                    })
                    st.session_state.grants_data = pd.concat([st.session_state.grants_data, new_data], ignore_index=True)
                    st.rerun()
        else:
            st.info("All grants have been added to your selection.")
        
        st.divider()
        
        # Generate schedule section
        st.subheader("Generate Schedule")
        
        # Show total hours before generating
        if not st.session_state.grants_data.empty:
            total_max_hours = st.session_state.grants_data["Maximum Hours"].sum()
            st.write(f"Total Maximum Hours: **{total_max_hours:.2f}**")
            
            if abs(total_max_hours - 80.0) < 0.1:  # More generous tolerance
                st.success("✅ Total is 80 hours - each day will be allocated exactly 8 hours.")
            else:
                st.info("Note: For exact 8-hour days, set total maximum hours to exactly 80.")
        
        if st.button("Generate Schedule", type="primary", use_container_width=True):
            if not st.session_state.grants_data.empty:
                with st.spinner("Generating..."):
                    # Generate schedule
                    schedule, grants = allocate_hours(st.session_state.grants_data)
                    
                    # Convert to DataFrames
                    st.session_state.schedule_df = create_schedule_dataframe(schedule, grants)
                    st.session_state.summary_df = create_summary_dataframe(schedule, grants)
                    
                    # Verify each day is exactly 8 hours if total is 80
                    total_max_hours = st.session_state.grants_data["Maximum Hours"].sum()
                    if abs(total_max_hours - 80.0) < 0.1:  # More generous tolerance
                        # Create a pivot table to get daily totals
                        pivot_data = pd.pivot_table(
                            st.session_state.schedule_df,
                            values="Hours",
                            index=["Week", "Day"],
                            aggfunc=sum
                        )
                        
                        # Check if all days have exactly 8 hours
                        # Use a tighter tolerance for verification
                        all_days_valid = True
                        for index, value in pivot_data.iterrows():
                            if abs(value["Hours"] - 8.0) > 0.01:  # Reduced tolerance for better precision
                                all_days_valid = False
                                st.warning(f"Day {index[1]} of Week {index[0]} has {value['Hours']:.2f} hours")
                        
                        # Verify total allocated matches expected 80 hours
                        total_allocated = pivot_data["Hours"].sum()
                        if abs(total_allocated - 80.0) > 0.01:
                            st.warning(f"Total allocated hours is {total_allocated:.2f}, not exactly 80.00")
                            all_days_valid = False
                        
                        if all_days_valid:
                            st.success("Schedule generated with exactly 8 hours per day and all 80 hours allocated!")
                        else:
                            st.warning("Schedule generated, but some days may not have exactly 8 hours or the total allocated is not exactly 80 hours.")
                    else:
                        st.success("Schedule generated!")
            else:
                st.error("Please add at least one grant")
        
        # CSV download buttons (replacing Excel download)
        if 'schedule_df' in st.session_state:
            st.subheader("Download Options")
            
            # Detailed schedule CSV
            schedule_csv = export_to_csv(st.session_state.schedule_df)
            schedule_b64 = base64.b64encode(schedule_csv).decode()
            st.markdown(
                f'<a href="data:file/csv;base64,{schedule_b64}" download="schedule_details.csv" '
                f'class="css-16idsys e16nr0p34">Download Schedule Details (CSV)</a>', 
                unsafe_allow_html=True
            )
            
            # Summary CSV
            summary_csv = export_to_csv(st.session_state.summary_df)
            summary_b64 = base64.b64encode(summary_csv).decode()
            st.markdown(
                f'<a href="data:file/csv;base64,{summary_b64}" download="schedule_summary.csv" '
                f'class="css-16idsys e16nr0p34">Download Schedule Summary (CSV)</a>', 
                unsafe_allow_html=True
            )
    
    with col2:
        st.subheader("Selected Grants")
        
        if not st.session_state.grants_data.empty:
            # Add a "Quick 80-Hour Setup" button
            if st.button("Quick 80-Hour Setup", use_container_width=True):
                # Calculate current total
                current_total = st.session_state.grants_data["Maximum Hours"].sum()
                if abs(current_total) < 0.01:  # If current total is zero
                    # Evenly distribute 80 hours among all selected grants
                    num_grants = len(st.session_state.grants_data)
                    hours_per_grant = 80.0 / num_grants
                    for idx in st.session_state.grants_data.index:
                        st.session_state.grants_data.at[idx, "Maximum Hours"] = hours_per_grant
                else:
                    # Scale existing values to sum to 80
                    scaling_factor = 80.0 / current_total
                    for idx in st.session_state.grants_data.index:
                        current_hours = st.session_state.grants_data.at[idx, "Maximum Hours"]
                        st.session_state.grants_data.at[idx, "Maximum Hours"] = current_hours * scaling_factor
                
                # Clear the schedule so it will be regenerated with new values
                if 'schedule_df' in st.session_state:
                    del st.session_state.schedule_df
                    del st.session_state.summary_df
                st.rerun()
            
            # Track if we need to update the dataframe
            update_needed = False
            
            # Create a custom display for selected grants with inline edit and delete buttons
            for idx, row in st.session_state.grants_data.iterrows():
                # Create a row with columns for grant name, hours input, and delete button
                col_name, col_hours, col_delete = st.columns([2, 1, 1])
                
                with col_name:
                    st.write(row["Grant Name"])
                
                with col_hours:
                    # Create a unique key for each input
                    input_key = f"edit_hours_{row['Grant Name']}_{idx}"
                    
                    # Check if there's an existing value in session state
                    current_value = st.session_state.get(input_key, str(row['Maximum Hours']))
                    
                    # Create text input for editing hours
                    new_hours_str = st.text_input(
                        "Hours",
                        value=current_value,
                        label_visibility="collapsed",
                        key=input_key
                    )
                    
                    # If value changed, update the dataframe
                    try:
                        new_hours = float(new_hours_str)
                        if new_hours != row['Maximum Hours']:
                            st.session_state.grants_data.at[idx, 'Maximum Hours'] = new_hours
                            update_needed = True
                    except ValueError:
                        st.error(f"Invalid number for {row['Grant Name']}")
                
                with col_delete:
                    if st.button("Delete", key=f"inline_del_{row['Grant Name']}", use_container_width=True):
                        st.session_state.grants_data = st.session_state.grants_data.drop(idx).reset_index(drop=True)
                        st.rerun()
                
                # Add a light divider between grants
                st.markdown('<hr style="margin: 0.25em 0; border: 0; border-top: 1px solid #eee;">', unsafe_allow_html=True)
            
            # If we made changes to the dataframe, rerun to update everything
            if update_needed and 'schedule_df' in st.session_state:
                # Clear the schedule so it will be regenerated with new values
                del st.session_state.schedule_df
                del st.session_state.summary_df
            
            # Clear all button
            if st.button("Clear All Grants", use_container_width=True):
                st.session_state.grants_data = pd.DataFrame(columns=["Grant Name", "Maximum Hours"])
                if 'schedule_df' in st.session_state:
                    del st.session_state.schedule_df
                    del st.session_state.summary_df
                st.rerun()
        else:
            st.info("No grants selected yet. Add grants from the list on the left.")
        
        # Results display
        if 'schedule_df' in st.session_state:
            st.divider()
            st.subheader("📊 Schedule Results")
            
            # Calculate overall totals for display
            total_hours = st.session_state.summary_df["Total Hours"].sum()
            max_hours = st.session_state.summary_df["Maximum Hours"].sum()
            
            # Create metrics at the top
            metrics_cols = st.columns(3)
            metrics_cols[0].metric("Total Allocated Hours", f"{total_hours:.2f}")
            
            # Calculate the total workday hours (10 days × 8 hours)
            total_workday_hours = 10 * 8.0
            metrics_cols[1].metric("Total Workday Hours", f"{total_workday_hours:.2f}")
            
            # Calculate percentage utilization of grants
            utilization = (total_hours / max_hours * 100) if max_hours > 0 else 0
            # Calculate percentage of workday hours filled
            workday_fill = (total_hours / total_workday_hours * 100)
            metrics_cols[2].metric("Grant Utilization", f"{utilization:.1f}%", 
                                  f"({workday_fill:.1f}% of workdays)")
            
            # Progress bar showing how much of the grants are used
            st.progress(min(total_hours / max_hours, 1.0) if max_hours > 0 else 0)
            
            # Enhanced tabs with icons
            tab1, tab2, tab3 = st.tabs(["📈 Summary", "📅 Weekly Schedule", "📋 Daily Details"])
            
            with tab1:
                # Summary view with styled dataframe
                st.write("### Grant Summary")
                
                # Calculate some color formatting for the dataframe
                def highlight_remaining(val):
                    if isinstance(val, float):
                        if val < 0:  # Should never happen but just in case
                            return 'background-color: #ffcccb'
                        elif val > 0:  # Remaining hours (under-allocated)
                            return 'background-color: #e6ffe6'
                    return ''
                
                # Apply styling
                styled_df = st.session_state.summary_df.style.applymap(
                    highlight_remaining, 
                    subset=['Remaining Hours']
                )
                
                # Display with better formatting
                st.dataframe(
                    styled_df,
                    column_config={
                        "Grant": st.column_config.TextColumn("Grant Name"),
                        "Week 1 Hours": st.column_config.NumberColumn("Week 1", format="%.2f"),
                        "Week 2 Hours": st.column_config.NumberColumn("Week 2", format="%.2f"),
                        "Total Hours": st.column_config.NumberColumn("Total Used", format="%.2f"),
                        "Maximum Hours": st.column_config.NumberColumn("Maximum", format="%.2f"),
                        "Remaining Hours": st.column_config.NumberColumn("Remaining", format="%.2f"),
                    },
                    use_container_width=True,
                    hide_index=True
                )
                
                # Add explanatory text
                st.caption("Green: Remaining hours available for allocation.")
                
            with tab2:
                # Weekly schedule view with better formatting
                for week in [1, 2]:
                    st.write(f"### Week {week}")
                    
                    # Filter by week and pivot
                    week_data = st.session_state.schedule_df[st.session_state.schedule_df["Week"] == week]
                    pivot = pd.pivot_table(
                        week_data,
                        values="Hours",
                        index=["Day"],
                        columns=["Grant"],
                        aggfunc=sum,
                        fill_value=0
                    )
                    
                    # Add daily totals
                    pivot["Daily Total"] = pivot.sum(axis=1)
                    
                    # Reorder days of the week
                    day_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
                    pivot = pivot.reindex(day_order)
                    
                    # Calculate daily utilization
                    day_utilization = pivot["Daily Total"].apply(lambda x: f"{(x/8)*100:.0f}%" if x > 0 else "0%")
                    pivot["Utilization"] = day_utilization
                    
                    # Create styled dataframe with color highlights for daily totals
                    def highlight_totals(s):
                        is_total = s.name == "Daily Total"
                        return ['background-color: #f2f2f2' if is_total else '' for _ in s]
                    
                    # Apply styling
                    styled_pivot = pivot.style.apply(highlight_totals, axis=1)
                    
                    # Display with better formatting
                    st.dataframe(styled_pivot, use_container_width=True)
                    
                    # Calculate week total
                    week_total = pivot["Daily Total"].sum()
                    st.info(f"Week {week} Total: {week_total:.2f} hours ({(week_total/40)*100:.0f}% of 40 hour week)")
                
            with tab3:
                # Detailed day-by-day breakdown
                st.write("### Daily Allocation Details")
                
                # Group by day for better visualization
                days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
                
                # Create expandable sections for each day
                for day in days:
                    with st.expander(f"{day}"):
                        for week in [1, 2]:
                            day_data = st.session_state.schedule_df[
                                (st.session_state.schedule_df["Day"] == day) & 
                                (st.session_state.schedule_df["Week"] == week)
                            ]
                            
                            if not day_data.empty:
                                st.write(f"**Week {week}**")
                                
                                # Sort by hours descending
                                day_data = day_data.sort_values("Hours", ascending=False)
                                
                                # Create a more visual representation
                                for _, row in day_data.iterrows():
                                    # Calculate width as percentage of 8 hours
                                    width = min(int(row["Hours"] / 8 * 100), 100)
                                    
                                    # Display as a custom progress bar
                                    st.write(f"{row['Grant']}: {row['Hours']:.2f} hours")
                                    st.progress(width / 100)
                                
                                # Show daily total
                                daily_total = day_data["Hours"].sum()
                                st.info(f"Total: {daily_total:.2f} hours ({(daily_total/8)*100:.0f}% of 8 hour day)")
                                
                                # Highlight if the day is exactly 8 hours (with more generous tolerance)
                                if abs(daily_total - 8.0) < 0.05:
                                    st.success("✓ Perfect 8-hour day!")
                            else:
                                st.write(f"No hours allocated for Week {week}")
                        
                        st.divider()

if __name__ == "__main__":
    main()