/**
 * Copyright 2026 The Drasi Authors
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

document.addEventListener('DOMContentLoaded', () => {
    let syncingTabs = false;
  
    document.body.addEventListener('shown.bs.tab', (event) => {
      if (syncingTabs) return;
  
      // Capture scroll position before tabs switch
      const scrollPosition = window.scrollY || window.pageYOffset;
  
      syncingTabs = true;
      const selectedLabel = event.target.textContent.trim();
  
      document.querySelectorAll('.nav-tabs').forEach(nav => {
        const matchingTab = Array.from(nav.querySelectorAll('button.nav-link'))
          .find(t => t.textContent.trim() === selectedLabel);
  
        if (matchingTab && matchingTab !== event.target && !matchingTab.classList.contains('active')) {
          bootstrap.Tab.getOrCreateInstance(matchingTab).show();
        }
      });
  
      syncingTabs = false;
  
      // Restore scroll position immediately after switching
      window.scrollTo({ top: scrollPosition });
    });
  });
  